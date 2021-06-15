# Copyright 2021 gRPC authors.
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
import logging

import dataclasses
from google.rpc import code_pb2
import tenacity

from framework.infrastructure import gcp

logger = logging.getLogger(__name__)


class IamV1(gcp.api.GcpProjectApiResource):

    @dataclasses.dataclass(frozen=True)
    class ServiceAccount:
        """An IAM service account.

        https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts#ServiceAccount
        Note: "etag" field is skipped because it's deprecated
        """
        name: str
        projectId: str
        uniqueId: str
        email: str
        oauth2ClientId: str
        displayName: str = ''
        description: str = ''
        disabled: bool = False

    def __init__(self, api_manager: gcp.api.GcpApiManager, project: str):
        super().__init__(api_manager.iam('v1'), project)

    def service_account_full_name(self, name):
        return f'projects/{self.project}/serviceAccounts/{name}'

    def get_service_account(self, name) -> ServiceAccount:
        result = self.api.projects().serviceAccounts().get(
            name=self.service_account_full_name(name)).execute()
        logger.debug('Loaded Service Account:\n%s',
                     self._resource_pretty_format(result))
        # TODO(sergiitk): dataclass
        return self.ServiceAccount(
            name=result['name'],
            projectId=result['projectId'],
            uniqueId=result['uniqueId'],
            email=result['email'],
            oauth2ClientId=result['oauth2ClientId'],
            description=result.get('description', ''),
            displayName=result.get('displayName', ''),
            disabled=result.get('disabled', False))


    # @property
    # def api_name(self) -> str:
    #     return 'networksecurity'
    #
    # @property
    # def api_version(self) -> str:
    #     return 'v1alpha1'
    #
    # def create_server_tls_policy(self, name, body: dict):
    #     return self._create_resource(self._api_locations.serverTlsPolicies(),
    #                                  body,
    #                                  serverTlsPolicyId=name)
    #
    # def get_server_tls_policy(self, name: str) -> ServerTlsPolicy:
    #     result = self._get_resource(
    #         collection=self._api_locations.serverTlsPolicies(),
    #         full_name=self.resource_full_name(name, self.SERVER_TLS_POLICIES))
    #
    #     return self.ServerTlsPolicy(name=name,
    #                                 url=result['name'],
    #                                 server_certificate=result.get(
    #                                     'serverCertificate', {}),
    #                                 mtls_policy=result.get('mtlsPolicy', {}),
    #                                 create_time=result['createTime'],
    #                                 update_time=result['updateTime'])
    #
    # def delete_server_tls_policy(self, name):
    #     return self._delete_resource(
    #         collection=self._api_locations.serverTlsPolicies(),
    #         full_name=self.resource_full_name(name, self.SERVER_TLS_POLICIES))
    #
    # def create_client_tls_policy(self, name, body: dict):
    #     return self._create_resource(self._api_locations.clientTlsPolicies(),
    #                                  body,
    #                                  clientTlsPolicyId=name)
    #
    # def get_client_tls_policy(self, name: str) -> ClientTlsPolicy:
    #     result = self._get_resource(
    #         collection=self._api_locations.clientTlsPolicies(),
    #         full_name=self.resource_full_name(name, self.CLIENT_TLS_POLICIES))
    #
    #     return self.ClientTlsPolicy(
    #         name=name,
    #         url=result['name'],
    #         client_certificate=result.get('clientCertificate', {}),
    #         server_validation_ca=result.get('serverValidationCa', []),
    #         create_time=result['createTime'],
    #         update_time=result['updateTime'])
    #
    # def delete_client_tls_policy(self, name):
    #     return self._delete_resource(
    #         collection=self._api_locations.clientTlsPolicies(),
    #         full_name=self.resource_full_name(name, self.CLIENT_TLS_POLICIES))
