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
import functools
import logging
import os
from typing import Any
from typing import Dict
from typing import Optional

from dataclasses import dataclass
import retrying
from googleapiclient import discovery
from googleapiclient import errors

logger = logging.getLogger(__name__)

# Constants
# todo(sergiitk): move somplace better
_WAIT_FOR_BACKEND_SEC = 1200
_WAIT_FOR_OPERATION_SEC = 1200
_WAIT_FIXES_SEC = 2
_GCP_API_RETRIES = 5


class GcpApiManager:
    def __init__(self, alpha_api_key=None):
        self.alpha_api_key = alpha_api_key or os.getenv('ALPHA_API_KEY')

    @functools.lru_cache(None)
    def compute(self, version):
        api_name = 'compute'
        if version == 'v1':
            return discovery.build(api_name, version, cache_discovery=False)
        raise NotImplementedError(f'Compute {version} not supported')

    @functools.lru_cache(None)
    def networksecurity(self, version):
        api_name = 'networksecurity'

        if version == 'v1alpha1':
            return discovery.build(
                api_name, version,
                discoveryServiceUrl=f'{discovery.V2_DISCOVERY_URI}'
                                    f'{self._key_param(self.alpha_api_key)}',
                cache_discovery=False)

        raise NotImplementedError(f'Network Security {version} not supported')

    @functools.lru_cache(None)
    def networkservices(self, version):
        api_name = 'networkservices'

        if version == 'v1alpha1':
            return discovery.build(
                api_name, version,
                discoveryServiceUrl=f'{discovery.V2_DISCOVERY_URI}'
                                    f'{self._key_param(self.alpha_api_key)}',
                cache_discovery=False)

        raise NotImplementedError(f'Network Services {version} not supported')

    @staticmethod
    def _key_param(key):
        return f'&key={key}' if key else ''

    def close(self):
        """todo(sergiitk): contextlib exitstack"""
        # if self._compute_v1:
        #     self._compute_v1.close()


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


class GcpProjectApiResource(object):
    def __init__(self, api: discovery.Resource, project: str):
        self.api: discovery.Resource = api
        self.project: str = project

    @staticmethod
    def wait_for_operation(operation_request,
                           test_success_fn,
                           timeout_sec=_WAIT_FOR_OPERATION_SEC,
                           wait_sec=_WAIT_FIXES_SEC):
        @retrying.retry(
            retry_on_result=lambda result: not test_success_fn(result),
            stop_max_delay=timeout_sec * 1000,
            wait_fixed=wait_sec * 1000)
        def _retry_until_status_done():
            logger.debug('Waiting for operation...')
            return operation_request.execute()

        return _retry_until_status_done()


class NetworkSecurityV1Alpha1(GcpProjectApiResource):
    API_NAME = 'networksecurity'
    API_VERSION = 'v1alpha1'
    DEFAULT_GLOBAL = 'global'
    SERVER_TLS_POLICIES = 'serverTlsPolicies'
    CLIENT_TLS_POLICIES = 'clientTlsPolicies'

    @dataclass
    class ServerTlsPolicy:
        url: str
        name: str
        server_certificate: dict
        mtls_policy: dict
        update_time: str
        create_time: str

    @dataclass
    class ClientTlsPolicy:
        url: str
        name: str
        client_certificate: dict
        server_validation_ca: list
        update_time: str
        create_time: str

    def __init__(self, api_manager: GcpApiManager, project: str):
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
        except errors.HttpError as error:
            # noinspection PyProtectedMember
            reason = error._get_reason()
            logger.info('Delete failed. Error: %s %s',
                        error.resp.status, reason)

    def _execute(self, request, timeout_sec=_WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=_GCP_API_RETRIES)
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


class NetworkServicesV1Alpha1(GcpProjectApiResource):
    API_NAME = 'networkservices'
    API_VERSION = 'v1alpha1'
    DEFAULT_GLOBAL = 'global'
    ENDPOINT_CONFIG_SELECTORS = 'endpointConfigSelectors'

    @dataclass
    class EndpointConfigSelector:
        url: str
        name: str
        type: str
        server_tls_policy: Optional[str]
        traffic_port_selector: dict
        endpoint_matcher: dict
        http_filters: dict
        update_time: str
        create_time: str

    def __init__(self, api_manager: GcpApiManager, project: str):
        super().__init__(api_manager.networkservices(self.API_VERSION), project)
        # Shortcut
        self._api_locations = self.api.projects().locations()

    def create_endpoint_config_selector(self, name, body: dict):
        return self._create_resource(
            self._api_locations.endpointConfigSelectors(),
            body, endpointConfigSelectorId=name)

    def get_endpoint_config_selector(self, name: str) -> EndpointConfigSelector:
        result = self._get_resource(
            collection=self._api_locations.endpointConfigSelectors(),
            full_name=self.resource_full_name(name,
                                              self.ENDPOINT_CONFIG_SELECTORS))

        return self.EndpointConfigSelector(
            name=name,
            url=result['name'],
            type=result['type'],
            server_tls_policy=result.get('serverTlsPolicy', None),
            traffic_port_selector=result['trafficPortSelector'],
            endpoint_matcher=result['endpointMatcher'],
            http_filters=result['httpFilters'],
            update_time=result['updateTime'],
            create_time=result['createTime'])

    def delete_endpoint_config_selector(self, name):
        return self._delete_resource(
            collection=self._api_locations.endpointConfigSelectors(),
            full_name=self.resource_full_name(name,
                                              self.ENDPOINT_CONFIG_SELECTORS))

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
        except errors.HttpError as error:
            # noinspection PyProtectedMember
            reason = error._get_reason()
            logger.info('Delete failed. Error: %s %s',
                        error.resp.status, reason)

    def _execute(self, request, timeout_sec=_WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=_GCP_API_RETRIES)

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


class ComputeV1(GcpProjectApiResource):
    def __init__(self, api_manager: GcpApiManager, project: str):
        super().__init__(api_manager.compute('v1'), project)

    class HealthCheckProtocol(enum.Enum):
        TCP = enum.auto()

    class BackendServiceProtocol(enum.Enum):
        HTTP2 = enum.auto()
        GRPC = enum.auto()

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

    def get_backend_service_traffic_director(self, name: str) -> GcpResource:
        return self._get_resource(self.api.backendServices(),
                                  backendService=name)

    def patch_backend_service(self, backend_service, body, **kwargs):
        self._patch_resource(
            collection=self.api.backendServices(),
            backendService=backend_service.name,
            body=body,
            **kwargs)

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

    def create_target_http_proxy(
        self,
        name: str,
        url_map: GcpResource,
    ) -> GcpResource:
        return self._insert_resource(self.api.targetHttpProxies(), {
            'name': name,
            'url_map': url_map.url,
        })

    def delete_target_http_proxy(self, name):
        self._delete_resource(self.api.targetHttpProxies(),
                              targetHttpProxy=name)

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
            except errors.HttpError as error:
                # noinspection PyProtectedMember
                reason = error._get_reason()
                logger.debug('Retrying NEG load, got %s, details %s',
                             error.resp.status, reason)
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

    def wait_for_backends_healthy_status(
        self,
        backend_service,
        backends,
        timeout_sec=_WAIT_FOR_OPERATION_SEC,
        wait_sec=_WAIT_FIXES_SEC,
    ):
        pending = set(backends)

        @retrying.retry(
            retry_on_result=lambda result: not result,
            stop_max_delay=timeout_sec * 1000,
            wait_fixed=wait_sec * 1000)
        def _retry_backends_health():
            for backend in pending:
                result = self.get_backend_service_backend_health(
                    backend_service, backend)

                if 'healthStatus' not in result:
                    logger.debug('Waiting for instances: backend %s, zone %s',
                                 backend.name, backend.zone)
                    continue

                backend_healthy = True
                for instance in result['healthStatus']:
                    logger.debug(
                        'Backend %s in zone %s: instance %s:%s health: %s',
                        backend.name, backend.zone,
                        instance['ipAddress'], instance['port'],
                        instance['healthState'])
                    if instance['healthState'] != 'HEALTHY':
                        backend_healthy = False

                if backend_healthy:
                    logger.info('Backend %s in zone %s reported healthy',
                                backend.name, backend.zone)
                    pending.remove(backend)

            return not pending

        _retry_backends_health()

    def get_backend_service_backend_health(self, backend_service, backend):
        return self.api.backendServices().getHealth(
            project=self.project, backendService=backend_service.name,
            body={"group": backend.url}).execute()

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
        except errors.HttpError as error:
            # noinspection PyProtectedMember
            reason = error._get_reason()
            logger.info('Delete failed. Error: %s %s',
                        error.resp.status, reason)

    def _execute(self, request, timeout_sec=_WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=_GCP_API_RETRIES)
        logger.debug('Response %s', operation)

        # todo(sergiitk) try using wait() here
        # https://googleapis.github.io/google-api-python-client/docs/dyn/compute_v1.globalOperations.html#wait
        operation_request = self.api.globalOperations().get(
            project=self.project, operation=operation['name'])

        logger.debug('Waiting for global operation %s, timeout %s sec',
                     operation['name'], timeout_sec)
        response = self.wait_for_operation(
            operation_request=operation_request,
            test_success_fn=lambda _result: _result['status'] == 'DONE',
            timeout_sec=timeout_sec)

        if 'error' in response:
            logger.debug('Waiting for global operation failed, response: %r',
                         response)
            raise Exception(f'Operation {operation["name"]} did not complete '
                            f'within {timeout_sec}, error={response["error"]}')
        return response
