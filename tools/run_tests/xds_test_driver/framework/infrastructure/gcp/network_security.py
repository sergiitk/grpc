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
import logging

import dataclasses
import googleapiclient.errors
from googleapiclient import discovery

from framework.infrastructure import gcp

logger = logging.getLogger(__name__)


class NetworkSecurityV1Alpha1(gcp.GcpProjectApiResource):
    API_NAME = 'networksecurity'
    API_VERSION = 'v1alpha1'
    DEFAULT_GLOBAL = 'global'
    SERVER_TLS_POLICIES = 'serverTlsPolicies'
    CLIENT_TLS_POLICIES = 'clientTlsPolicies'

    # todo(sergiitk): move someplace better
    _WAIT_FOR_OPERATION_SEC = 1200
    _GCP_API_RETRIES = 5

    @dataclasses.dataclass
    class ServerTlsPolicy:
        url: str
        name: str
        server_certificate: dict
        mtls_policy: dict
        update_time: str
        create_time: str

    @dataclasses.dataclass
    class ClientTlsPolicy:
        url: str
        name: str
        client_certificate: dict
        server_validation_ca: list
        update_time: str
        create_time: str

    def __init__(self, api_manager: gcp.GcpApiManager, project: str):
        super().__init__(api_manager.networksecurity(self.API_VERSION), project)
        # Shortcut
        self._api_locations = self.api.projects().locations()

    def create_server_tls_policy(self, name, body: dict):
        return self._create_resource(
            self._api_locations.serverTlsPolicies(),
            body, serverTlsPolicyId=name)

    def get_server_tls_policy(self, name: str) -> ServerTlsPolicy:
        result = self._get_resource(
            collection=self._api_locations.serverTlsPolicies(),
            full_name=self.resource_full_name(name, self.SERVER_TLS_POLICIES))

        return self.ServerTlsPolicy(
            name=name,
            url=result['name'],
            server_certificate=result.get('serverCertificate', {}),
            mtls_policy=result.get('mtlsPolicy', {}),
            create_time=result['createTime'],
            update_time=result['updateTime'])

    def delete_server_tls_policy(self, name):
        return self._delete_resource(
            collection=self._api_locations.serverTlsPolicies(),
            full_name=self.resource_full_name(name, self.SERVER_TLS_POLICIES))

    def create_client_tls_policy(self, name, body: dict):
        return self._create_resource(
            self._api_locations.clientTlsPolicies(),
            body, clientTlsPolicyId=name)

    def get_client_tls_policy(self, name: str) -> ClientTlsPolicy:
        result = self._get_resource(
            collection=self._api_locations.clientTlsPolicies(),
            full_name=self.resource_full_name(name, self.CLIENT_TLS_POLICIES))

        return self.ClientTlsPolicy(
            name=name,
            url=result['name'],
            client_certificate=result.get('clientCertificate', {}),
            server_validation_ca=result.get('serverValidationCa', []),
            create_time=result['createTime'],
            update_time=result['updateTime'])

    def delete_client_tls_policy(self, name):
        return self._delete_resource(
            collection=self._api_locations.clientTlsPolicies(),
            full_name=self.resource_full_name(name, self.CLIENT_TLS_POLICIES))

    def parent(self, location=None):
        if not location:
            location = self.DEFAULT_GLOBAL
        return f'projects/{self.project}/locations/{location}'

    def resource_full_name(self, name, collection_name):
        return f'{self.parent()}/{collection_name}/{name}'

    def _create_resource(self, collection: discovery.Resource, body: dict,
                         **kwargs):
        logger.debug("Creating %s", body)
        create_req = collection.create(parent=self.parent(),
                                       body=body, **kwargs)
        self._execute(create_req)

    @staticmethod
    def _get_resource(collection: discovery.Resource, full_name):
        resource = collection.get(name=full_name).execute()
        logger.debug("Loaded %r", resource)
        return resource

    def _delete_resource(self, collection: discovery.Resource, full_name: str):
        logger.debug("Deleting %s", full_name)
        try:
            self._execute(collection.delete(name=full_name))
        except googleapiclient.errors.HttpError as error:
            # noinspection PyProtectedMember
            reason = error._get_reason()
            logger.info('Delete failed. Error: %s %s',
                        error.resp.status, reason)

    def _execute(self, request, timeout_sec=_WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=self._GCP_API_RETRIES)
        self._wait(operation, timeout_sec)

    def _wait(self, operation, timeout_sec=_WAIT_FOR_OPERATION_SEC):
        op_name = operation['name']
        logger.debug('Waiting for %s operation, timeout %s sec: %s',
                     self.API_NAME, timeout_sec, op_name)

        op_request = self._api_locations.operations().get(name=op_name)
        op_completed = self.wait_for_operation(
            operation_request=op_request,
            test_success_fn=lambda result: result['done'],
            timeout_sec=timeout_sec)

        logger.debug('Completed operation: %s', op_completed)
        if 'error' in op_completed:
            # todo(sergiitk): custom exception
            raise Exception(f'Waiting for {self.API_NAME} operation {op_name} '
                            f'failed. Error: {op_completed["error"]}')
