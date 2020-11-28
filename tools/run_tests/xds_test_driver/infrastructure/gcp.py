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

    def _insert_resource(
        self,
        collection: discovery.Resource,
        body: Dict[str, Any]
    ) -> GcpResource:
        logger.debug("Creating %s", body)
        resp = self._execute(collection.insert(project=self.project, body=body))
        return GcpResource(body['name'], resp['targetLink'])

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

# def wait_for_global_operation(compute, project, operation,
#                               timeout_sec=_WAIT_FOR_OPERATION_SEC,
#                               wait_sec=_WAIT_FIXES_SEC):
#
#     @retrying.retry(retry_on_result=lambda result: result['status'] != 'DONE',
#                     stop_max_delay=timeout_sec * 1000,
#                     wait_fixed=wait_sec * 1000)
#     def _retry_until_status_done():
#         logger.debug('Waiting for operation %s', operation)
#         return compute.globalOperations().get(
#             project=project, operation=operation).execute()
#
#     response = _retry_until_status_done()
#     if 'error' in response:
#         raise Exception(f'Operation {operation} did not complete '
#                         f'within {timeout_sec}, error={response["error"]}')
#
#
# @retrying.retry(retry_on_result=lambda result: not result,
#                 stop_max_delay=_WAIT_FOR_BACKEND_SEC * 1000,
#                 wait_fixed=_WAIT_FIXES_SEC * 1000)
# def wait_for_backends_healthy_status(compute, project,
#                                      backend_service, backends):
#     # todo(sergiitk): match with the expectation how many instances in each zone
#     for backend in backends:
#         logger.info(
#             "Requesting Backend Service %s health: backend %s, zone %s",
#             backend_service.name, backend.name, backend.zone)
#         result = compute.backendServices().getHealth(
#             project=project, backendService=backend_service.name,
#             body={"group": backend.url}).execute()
#         logger.debug('%s health: %s', backend.name, result)
#         if 'healthStatus' not in result:
#             logger.debug('Backend %s in zone %s: no instances found',
#                           backend.name, backend.zone)
#             return False
#
#         for instance in result['healthStatus']:
#             logger.debug(
#                 'Backend %s in zone %s: instance %s:%s - health state: %s',
#                 backend.name, backend.zone,
#                 instance['ipAddress'], instance['port'],
#                 instance['healthState'])
#
#             if instance['healthState'] != 'HEALTHY':
#                 logger.info(
#                     'Backend %s zone %s: endpoint %s:%s healthy',
#                     backend.name, backend.zone,
#                     instance['ipAddress'], instance['port'])
#                 return False
#
#     return True
#
#
# def get_health_check(compute, project, health_check_name):
#     result = compute.healthChecks().get(project=project,
#                                         healthCheck=health_check_name).execute()
#     return GcpResource(health_check_name, result['selfLink'])
#
#
# def create_tcp_health_check(compute, project, health_check_name):
#     tcp_health_check_spec = {
#         'name': health_check_name,
#         'type': 'TCP',
#         'tcpHealthCheck': {
#             'portSpecification': 'USE_SERVING_PORT',
#         }
#     }
#     result = compute.healthChecks().insert(
#         project=project,
#         body=tcp_health_check_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(compute, project, result['name'])
#     return GcpResource(result['name'], result['targetLink'])
#
#
# def get_backend_service(compute, project, backend_service_name):
#     result = compute.backendServices().get(
#         project=project,
#         backendService=backend_service_name).execute()
#     return GcpResource(backend_service_name, result['selfLink'])
#
#
# def create_backend_service(compute, project,
#                            backend_service_name,
#                            health_check):
#     backend_service_spec = {
#         'name': backend_service_name,
#         'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
#         'healthChecks': [health_check.url],
#         'protocol': 'HTTP2',
#     }
#     result = compute.backendServices().insert(
#         project=project,
#         body=backend_service_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(compute, project, result['name'])
#     return GcpResource(backend_service_name, result['targetLink'])
#
#
# def backend_service_add_backend(compute, project,
#                                 backend_service, negs):
#     backends = [{
#         'group': neg.url,
#         'balancingMode': 'RATE',
#         'maxRatePerEndpoint': 5
#     } for neg in negs]
#
#     result = compute.backendServices().patch(
#         project=project,
#         backendService=backend_service.name,
#         body={'backends': backends}).execute(num_retries=_GCP_API_RETRIES)
#
#     wait_for_global_operation(
#         compute, project, result['name'], timeout_sec=_WAIT_FOR_BACKEND_SEC)
#
#
# def get_network_endpoint_group(compute, project, zone, neg_name):
#     # todo: retry
#     result = compute.networkEndpointGroups().get(
#         project=project,
#         zone=zone,
#         networkEndpointGroup=neg_name).execute()
#     return ZonalGcpResource(neg_name, result['selfLink'], zone)
#
#
# def create_url_map(compute, project,
#                    url_map_name, url_map_path_matcher_name,
#                    xds_service, backend_service):
#     url_map_spec = {
#         'name': url_map_name,
#         'defaultService': backend_service.url,
#         'pathMatchers': [{
#             'name': url_map_path_matcher_name,
#             'defaultService': backend_service.url,
#         }],
#         'hostRules': [{
#             'hosts': [xds_service],
#             'pathMatcher': url_map_path_matcher_name,
#         }]
#     }
#     result = compute.urlMaps().insert(
#         project=project,
#         body=url_map_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(compute, project, result['name'])
#     return GcpResource(url_map_name, result['targetLink'])
#
#
# def create_forwarding_rule(compute, project,
#                            forwarding_rule_name, xds_service_port,
#                            target_proxy, network):
#     forwarding_rule_spec = {
#         'name': forwarding_rule_name,
#         'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
#         'portRange': xds_service_port,
#         'IPAddress': '0.0.0.0',
#         'network': network,
#         'target': target_proxy.url,
#     }
#     result = compute.globalForwardingRules().insert(
#         project=project,
#         body=forwarding_rule_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(compute, project, result['name'])
#     return GcpResource(forwarding_rule_name, result['targetLink'])
#
#
# def get_url_map(compute, project, url_map_name):
#     result = compute.urlMaps().get(project=project,
#                                    urlMap=url_map_name).execute()
#     return GcpResource(url_map_name, result['selfLink'])
#
#
# def get_forwarding_rule(compute, project, forwarding_rule_name):
#     result = compute.globalForwardingRules().get(
#         project=project, forwardingRule=forwarding_rule_name).execute()
#     return GcpResource(forwarding_rule_name, result['selfLink'])
#
#
# def create_target_proxy(compute, project, target_proxy_name, url_map):
#     target_proxy_spec = {
#         'name': target_proxy_name,
#         'url_map': url_map.url,
#         # 'validate_for_proxyless': True,
#     }
#     # result = compute.targetGrpcProxies().insert(
#     #     project=project,
#     #     body=target_proxy_spec).execute(num_retries=_GCP_API_RETRIES)
#     result = compute.targetHttpProxies().insert(
#         project=project,
#         body=target_proxy_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(compute, project, result['name'])
#     return GcpResource(target_proxy_name, result['targetLink'])
#
#
# def get_target_proxy(compute, project, target_proxy_name):
#     result = compute.targetGrpcProxies().get(
#         project=project, targetGrpcProxy=target_proxy_name).execute()
#     return GcpResource(target_proxy_name, result['selfLink'])
