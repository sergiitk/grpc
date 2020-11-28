# Copyright 2016 gRPC authors.
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
import enum
import logging
from typing import Any
from typing import Dict
from typing import Optional

import retrying
from googleapiclient import discovery
from googleapiclient import errors

logger = logging.getLogger(__name__)

# Constants
_WAIT_FOR_BACKEND_SEC = 1200
_WAIT_FOR_OPERATION_SEC = 1200
_WAIT_FIXES_SEC = 2
_GCP_API_RETRIES = 5


class GcpResource:
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.url!r})'


class ZonalGcpResource(GcpResource):
    def __init__(self, name, url, zone):
        super().__init__(name, url)
        self.zone = zone

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.url!r}, ' \
               f'{self.zone!r})'


class GcpRequestTimeoutError(Exception):
    """Request timeout"""


class GcpApiManager:
    def __init__(self):
        self._compute_v1: Optional[discovery.Resource] = None

    @property
    def compute_v1(self):
        if not self._compute_v1:
            self._compute_v1 = discovery.build(
                'compute', 'v1', cache_discovery=False)
        return self._compute_v1

    def close(self):
        if self._compute_v1:
            self._compute_v1.close()


class GCloud:
    def __init__(self, api: GcpApiManager, project: str):
        # todo(sergiitk): remove this class
        self.api: GcpApiManager = api
        self.project: str = project
        self.compute: ComputeV1 = ComputeV1(self.api.compute_v1,
                                            project=project)


class Compute:
    def __init__(self, compute_api: discovery.Resource, project: str):
        self.api: discovery.Resource = compute_api
        self.project: str = project


class ComputeV1(Compute):
    class HealthCheckProtocol(enum.Enum):
        TCP = enum.auto()

    class BackendServiceProtocol(enum.Enum):
        HTTP2 = enum.auto()
        GRPC = enum.auto()

    def wait_for_global_operation(self,
                                  operation,
                                  timeout_sec=_WAIT_FOR_OPERATION_SEC,
                                  wait_sec=_WAIT_FIXES_SEC):
        @retrying.retry(
            retry_on_result=lambda result: result['status'] != 'DONE',
            stop_max_delay=timeout_sec * 1000,
            wait_fixed=wait_sec * 1000)
        def _retry_until_status_done():
            # todo(sergiitk) try using wait() here
            # https://googleapis.github.io/google-api-python-client/docs/dyn/compute_v1.globalOperations.html#wait
            return self.api.globalOperations().get(
                project=self.project, operation=operation).execute()

        logger.debug('Waiting for global operation %s', operation)
        response = _retry_until_status_done()
        if 'error' in response:
            logger.debug('Waiting for global op failed, response: %r', response)
            raise Exception(f'Operation {operation} did not complete '
                            f'within {timeout_sec}, error={response["error"]}')

    def create_health_check_tcp(self, name,
                                use_serving_port=False) -> GcpResource:
        health_check_settings = {}
        if use_serving_port:
            health_check_settings['portSpecification'] = 'USE_SERVING_PORT'

        return self._insert_resource(self.api.healthChecks(), {
            'name': name,
            'type': 'TCP',
            'tcpHealthCheck': health_check_settings,
        })

    def delete_health_check(self, name):
        self._delete_resource(self.api.healthChecks(), healthCheck=name)

    def create_backend_service_traffic_director(
        self,
        name: str,
        health_check: GcpResource,
        protocol: Optional[BackendServiceProtocol] = None
    ) -> GcpResource:
        if not isinstance(protocol, self.BackendServiceProtocol):
            raise TypeError(f'Unexpected Backend Service protocol: {protocol}')
        return self._insert_resource(self.api.backendServices(), {
            'name': name,
            'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
            'healthChecks': [health_check.url],
            'protocol': protocol.name,
        })

    def backend_service_add_backends(self, backend_service, backends):
        backend_list = [{
            'group': backend.url,
            'balancingMode': 'RATE',
            'maxRatePerEndpoint': 5
        } for backend in backends]

        self._patch_resource(
            collection=self.api.backendServices(),
            body={'backends': backend_list},
            backendService=backend_service.name)

    def delete_backend_service(self, name):
        self._delete_resource(self.api.backendServices(), backendService=name)

    def create_url_map(
        self,
        name: str,
        matcher_name: str,
        src_hosts,
        dst_default_backend_service: GcpResource,
        dst_host_rule_match_backend_service: Optional[GcpResource] = None,
    ) -> GcpResource:
        if dst_host_rule_match_backend_service is None:
            dst_host_rule_match_backend_service = dst_default_backend_service
        return self._insert_resource(self.api.urlMaps(), {
            'name': name,
            'defaultService': dst_default_backend_service.url,
            'hostRules': [{
                'hosts': src_hosts,
                'pathMatcher': matcher_name,
            }],
            'pathMatchers': [{
                'name': matcher_name,
                'defaultService': dst_host_rule_match_backend_service.url,
            }],
        })

    def delete_url_map(self, name):
        self._delete_resource(self.api.urlMaps(), urlMap=name)

    def create_target_grpc_proxy(
        self,
        name: str,
        url_map: GcpResource,
    ) -> GcpResource:
        return self._insert_resource(self.api.targetGrpcProxies(), {
            'name': name,
            'url_map': url_map.url,
            'validate_for_proxyless': True,
        })

    def delete_target_grpc_proxy(self, name):
        self._delete_resource(self.api.targetGrpcProxies(),
                              targetGrpcProxy=name)

    def create_forwarding_rule(
        self,
        name: str,
        src_port: int,
        target_proxy: GcpResource,
        network_url: str,
    ) -> GcpResource:
        return self._insert_resource(self.api.globalForwardingRules(), {
            'name': name,
            'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
            'portRange': src_port,
            'IPAddress': '0.0.0.0',
            'network': network_url,
            'target': target_proxy.url,
        })

    def delete_forwarding_rule(self, name):
        self._delete_resource(self.api.globalForwardingRules(),
                              forwardingRule=name)

    def wait_for_network_endpoint_group(self, name, zone):
        @retrying.retry(retry_on_result=lambda r: not r,
                        stop_max_delay=60 * 1000,
                        wait_fixed=1 * 1000)
        def _wait_for_network_endpoint_group():
            try:
                neg = self.get_network_endpoint_group(name, zone)
            except errors.HttpError as e:
                logger.debug('Retrying NEG load, got %s, details %s',
                             e.resp.status, e.error_details)
                raise
            if not neg:
                logger.error('Unexpected state: no error, but NEG not loaded')
                raise RuntimeError('Unexpected state loading NEG')
            logger.info('Loaded NEG %s, zone %s', neg.name, neg.zone)
            return neg

        return _wait_for_network_endpoint_group()

    def get_network_endpoint_group(self, name, zone):
        resource = self._get_resource(self.api.networkEndpointGroups(),
                                      networkEndpointGroup=name, zone=zone)
        # @todo(sergiitk): fix
        return ZonalGcpResource(resource.name, resource.url, zone)

    def _get_resource(self, collection: discovery.Resource,
                      **kwargs) -> GcpResource:
        resp = collection.get(project=self.project, **kwargs).execute()
        logger.debug("Loaded %r", resp)
        return GcpResource(resp['name'], resp['selfLink'])

    def _insert_resource(
        self,
        collection: discovery.Resource,
        body: Dict[str, Any]
    ) -> GcpResource:
        logger.debug("Creating %s", body)
        resp = self._execute(collection.insert(project=self.project, body=body))
        return GcpResource(body['name'], resp['targetLink'])

    def _patch_resource(self, collection, body, **kwargs):
        logger.debug("Patching %s", body)
        self._execute(
            collection.patch(project=self.project, body=body, **kwargs))

    def _delete_resource(self, collection, **kwargs):
        try:
            self._execute(collection.delete(project=self.project, **kwargs))
            return True
        except errors.HttpError as e:
            logger.info('Delete failed: %s', e)

    def _execute(self, request):
        operation = request.execute(num_retries=_GCP_API_RETRIES)
        self.wait_for_global_operation(operation['name'])
        return operation
