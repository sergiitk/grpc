# Copyright 2020 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import contextlib
import functools
from typing import List, Optional

from google.cloud import secretmanager_v1
from googleapiclient import discovery

from framework.infrastructure.gcp import gcp_flags


class GcpApiClientManager:
    """Manage raw access to GCP API services.

    Abstracts out the logic of building heterogeneous API clients.
    1) Builds dynamic APIs clients using:
        - local discovery documents available a file
        - remote discovery documents available via v1 and v2 discovery URIs
        - remote private APIs protected with visibility labels
    2) Manages API client lifecycle:
        - lazy-load and cache dynamic clients
        - provides `close()` to shut down active remote connections
    3) Allows mixing Google API Client Libraries and Google Cloud Client
       Libraries: https://cloud.google.com/apis/docs/client-libraries-explained

    Google API Client Libraries:
    - https://github.com/googleapis/google-api-python-client/
    - https://googleapis.github.io/google-api-python-client/docs/start.html
    - API List: https://googleapis.github.io/google-api-python-client/docs/dyn/
    - Reference: https://googleapis.github.io/google-api-python-client/docs/epy/

    Google Cloud Client Libraries:
    - https://cloud.google.com/apis/docs/cloud-client-libraries
    - https://github.com/googleapis/google-cloud-python

    Client Libraries usage samples:
    - https://github.com/GoogleCloudPlatform/python-docs-samples
    """

    def __init__(self,
                 *,
                 v1_discovery_uri=None,
                 v2_discovery_uri=None,
                 compute_v1_discovery_file=None,
                 private_api_key_secret_name=None):
        self.v1_discovery_uri = (v1_discovery_uri or
                                 gcp_flags.V1_DISCOVERY_URI.value)
        self.v2_discovery_uri = (v2_discovery_uri or
                                 gcp_flags.V2_DISCOVERY_URI.value)
        self.compute_v1_discovery_file = (
            compute_v1_discovery_file or
            gcp_flags.COMPUTE_V1_DISCOVERY_FILE.value)
        self.private_api_key_secret_name = (
            private_api_key_secret_name or
            gcp_flags.PRIVATE_API_KEY_SECRET_NAME.value)
        # TODO(sergiitk): add options to pass google Credentials
        self._exit_stack = contextlib.ExitStack()

    def close(self):
        self._exit_stack.close()

    @functools.lru_cache(None)
    def compute(self, version):
        """Compute Engine API dynamic client

        https://googleapis.github.io/google-api-python-client/docs/dyn/compute_v1.html
        https://cloud.google.com/compute/docs/reference/rest/v1
        https://cloud.google.com/compute/docs/tutorials/python-guide
        """
        api_name = 'compute'
        if version == 'v1':
            if self.compute_v1_discovery_file:
                return self._build_client_from_file(
                    self.compute_v1_discovery_file)
            else:
                return self._build_client_from_discovery_v1(api_name, version)

        raise NotImplementedError(f'Compute {version} not supported')

    @functools.lru_cache(None)
    def networksecurity(self, version):
        """Network Security dynamic client"""
        api_name = 'networksecurity'
        if version == 'v1alpha1':
            return self._build_client_from_discovery_v2(
                api_name,
                version,
                api_key=self._private_api_key,
                visibility_labels=['NETWORKSECURITY_ALPHA'])

        raise NotImplementedError(f'Network Security {version} not supported')

    @functools.lru_cache(None)
    def networkservices(self, version):
        """Network Services dynamic client"""
        api_name = 'networkservices'
        if version == 'v1alpha1':
            return self._build_client_from_discovery_v2(
                api_name,
                version,
                api_key=self._private_api_key,
                visibility_labels=['NETWORKSERVICES_ALPHA'])

        raise NotImplementedError(f'Network Services {version} not supported')

    @functools.lru_cache(None)
    def secrets(self, version):
        """Secret Manager API Cloud Client Library

        https://github.com/googleapis/python-secret-manager
        https://googleapis.dev/python/secretmanager/latest/index.html
        https://cloud.google.com/secret-manager/docs/reference/rest
        https://cloud.google.com/secret-manager/docs/reference/libraries
        """
        if version == 'v1':
            return secretmanager_v1.SecretManagerServiceClient()

        raise NotImplementedError(f'Secret Manager {version} not supported')

    @property
    @functools.lru_cache(None)
    def _private_api_key(self):
        """Load private API key.

        Return API key credential that identifies a GCP project allow-listed for
        accessing private API discovery documents.
        https://pantheon.corp.google.com/apis/credentials

        This method lazy-loads the content of the key from the Secret Manager.
        https://pantheon.corp.google.com/security/secret-manager
        """
        if not self.private_api_key_secret_name:
            raise ValueError('private_api_key_secret_name must be set to '
                             'access private_api_key.')

        secrets_api = self.secrets('v1')
        version_resource_path = secrets_api.secret_version_path(
            **secrets_api.parse_secret_path(self.private_api_key_secret_name),
            secret_version='latest')
        secret: secretmanager_v1.AccessSecretVersionResponse
        secret = secrets_api.access_secret_version(name=version_resource_path)
        return secret.payload.data.decode()

    def _build_client_from_discovery_v1(self, api_name, version):
        api_client = discovery.build(api_name,
                                     version,
                                     cache_discovery=False,
                                     discoveryServiceUrl=self.v1_discovery_uri)
        self._exit_stack.enter_context(api_client)
        return api_client

    def _build_client_from_discovery_v2(
            self,
            api_name,
            version,
            *,
            api_key: Optional[str] = None,
            visibility_labels: Optional[List] = None):
        params = {}
        if api_key:
            params['key'] = api_key
        if visibility_labels:
            # Dash-separated list of labels.
            params['labels'] = '_'.join(visibility_labels)

        params_str = ''
        if params:
            params_str = '&' + ('&'.join(f'{k}={v}' for k, v in params.items()))

        api_client = discovery.build(
            api_name,
            version,
            cache_discovery=False,
            discoveryServiceUrl=f'{self.v2_discovery_uri}{params_str}')
        self._exit_stack.enter_context(api_client)
        return api_client

    def _build_client_from_file(self, discovery_file):
        with open(discovery_file, 'r') as f:
            api_client = discovery.build_from_document(f.read())
        self._exit_stack.enter_context(api_client)
        return api_client
