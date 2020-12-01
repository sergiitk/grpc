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
import logging
from typing import Optional

from framework.infrastructure import gcp

logger = logging.getLogger(__name__)

# Type aliases
ComputeV1 = gcp.ComputeV1
HealthCheckProtocol = ComputeV1.HealthCheckProtocol
BackendServiceProtocol = ComputeV1.BackendServiceProtocol


class TrafficDirectorManager:
    compute: ComputeV1
    BACKEND_SERVICE_NAME = "backend-service"
    HEALTH_CHECK_NAME = "health-check"
    URL_MAP_NAME = "url-map"
    URL_MAP_PATH_MATCHER_NAME = "path-matcher"
    TARGET_PROXY_NAME = "target-proxy"
    FORWARDING_RULE_NAME = "forwarding-rule"

    def __init__(
        self,
        gcp_api_manager: gcp.GcpApiManager,
        project: str,
        *,
        resource_prefix: str,
        network: str = 'default',
    ):
        # Api
        self.compute = gcp.ComputeV1(gcp_api_manager, project)

        # Settings
        self.project: str = project
        self.network: str = network
        self.resource_prefix: str = resource_prefix

        # Mutable state
        self.health_check: Optional[gcp.GcpResource] = None
        self.backend_service: Optional[gcp.GcpResource] = None
        self.url_map: Optional[gcp.GcpResource] = None
        self.target_proxy: Optional[gcp.GcpResource] = None
        # todo(sergiitk): fix
        self.target_proxy_is_http = False
        self.forwarding_rule: Optional[gcp.GcpResource] = None
        self.backends = set()

    @property
    def network_url(self):
        return f'global/networks/{self.network}'

    def setup_for_grpc(
        self,
        service_host,
        service_port,
        *,
        backend_protocol=BackendServiceProtocol.GRPC
    ):
        self.create_health_check()
        self.create_backend_service(protocol=backend_protocol)
        self.create_url_map(service_host, service_port)
        if backend_protocol is BackendServiceProtocol.GRPC:
            self.create_target_grpc_proxy()
        else:
            self.create_target_http_proxy()
        self.create_forwarding_rule(service_port)

    def cleanup(self, *, force=False):
        # Cleanup in the reverse order of creation
        self.delete_forwarding_rule(force=force)
        if self.target_proxy_is_http:
            self.delete_target_http_proxy(force=force)
        else:
            self.delete_target_grpc_proxy(force=force)
        self.delete_url_map(force=force)
        self.delete_backend_service(force=force)
        self.delete_health_check(force=force)

    def _ns_name(self, name):
        return f'{self.resource_prefix}-{name}'

    def create_health_check(self, protocol=HealthCheckProtocol.TCP):
        if self.health_check:
            raise ValueError('Health check %s already created, delete it first',
                             self.health_check.name)
        name = self._ns_name(self.HEALTH_CHECK_NAME)
        logger.info('Creating %s Health Check %s', protocol.name, name)
        if protocol is HealthCheckProtocol.TCP:
            resource = self.compute.create_health_check_tcp(
                name, use_serving_port=True)
        else:
            raise ValueError('Unexpected protocol')
        self.health_check = resource

    def delete_health_check(self, force=False):
        if force:
            name = self._ns_name(self.HEALTH_CHECK_NAME)
        elif self.health_check:
            name = self.health_check.name
        else:
            return
        logger.info('Deleting Health Check %s', name)
        self.compute.delete_health_check(name)
        self.health_check = None

    def create_backend_service(
        self,
        protocol: BackendServiceProtocol = BackendServiceProtocol.GRPC
    ):
        name = self._ns_name(self.BACKEND_SERVICE_NAME)
        logger.info('Creating %s Backend Service %s', protocol.name, name)
        resource = self.compute.create_backend_service_traffic_director(
            name, health_check=self.health_check, protocol=protocol)
        self.backend_service = resource

    def delete_backend_service(self, force=False):
        if force:
            name = self._ns_name(self.BACKEND_SERVICE_NAME)
        elif self.backend_service:
            name = self.backend_service.name
        else:
            return
        logger.info('Deleting Backend Service %s', name)
        self.compute.delete_backend_service(name)
        self.backend_service = None

    def backend_service_add_neg_backends(self, name, zones):
        logger.info('Loading NEGs')
        for zone in zones:
            backend = self.compute.wait_for_network_endpoint_group(name, zone)
            self.backends.add(backend)

        # logger.info('Fake waiting before adding backends to avoid error '
        #             '400 RESOURCE_NOT_READY')
        # todo(sergiitk): figure out how to confirm NEG is ready to be added
        # time.sleep(10)
        self.backend_service_add_backends()
        self.wait_for_backends_healthy_status()

    def backend_service_add_backends(self):
        logging.info('Adding backends to Backend Service %s: %r',
                     self.backend_service.name, self.backends)
        self.compute.backend_service_add_backends(
            self.backend_service, self.backends)

    def backend_service_apply_client_mtls_policy(
        self,
        client_policy_url,
        server_spiffe
    ):
        logging.info('Adding Client mTls Policy to Backend Service %s: %s, '
                     'server %s',
                     self.backend_service.name,
                     client_policy_url,
                     server_spiffe)
        self.compute.patch_backend_service(self.backend_service, {
            'securitySettings': {
                'clientTlsPolicy': client_policy_url,
                'subjectAltNames': [server_spiffe]
            }})

    def wait_for_backends_healthy_status(self):
        logger.debug(
            "Waiting for Backend Service %s to report all backends healthy %r",
            self.backend_service, self.backends)
        self.compute.wait_for_backends_healthy_status(
            self.backend_service, self.backends)

    def create_url_map(
        self,
        src_host: str,
        src_port: int,
    ) -> gcp.GcpResource:
        src_address = f'{src_host}:{src_port}'
        name = self._ns_name(self.URL_MAP_NAME)
        matcher_name = self._ns_name(self.URL_MAP_PATH_MATCHER_NAME)
        logger.info('Creating URL map %s %s -> %s',
                    name, src_address, self.backend_service.name)
        resource = self.compute.create_url_map(
            name, matcher_name, [src_address], self.backend_service)
        self.url_map = resource
        return resource

    def delete_url_map(self, force=False):
        if force:
            name = self._ns_name(self.URL_MAP_NAME)
        elif self.url_map:
            name = self.url_map.name
        else:
            return
        logger.info('Deleting URL Map %s', name)
        self.compute.delete_url_map(name)
        self.url_map = None

    def create_target_grpc_proxy(self):
        # todo: different kinds
        name = self._ns_name(self.TARGET_PROXY_NAME)
        logger.info('Creating target GRPC proxy %s to url map %s',
                    name, self.url_map.name)
        resource = self.compute.create_target_grpc_proxy(
            name, self.url_map)
        self.target_proxy = resource

    def delete_target_grpc_proxy(self, force=False):
        if force:
            name = self._ns_name(self.TARGET_PROXY_NAME)
        elif self.target_proxy:
            name = self.target_proxy.name
        else:
            return
        logger.info('Deleting Target GRPC proxy %s', name)
        self.compute.delete_target_grpc_proxy(name)
        self.target_proxy = None
        self.target_proxy_is_http = False

    def create_target_http_proxy(self):
        # todo: different kinds
        name = self._ns_name(self.TARGET_PROXY_NAME)
        logger.info('Creating target HTTP proxy %s to url map %s',
                    name, self.url_map.name)
        resource = self.compute.create_target_http_proxy(
            name, self.url_map)
        self.target_proxy = resource
        self.target_proxy_is_http = True

    def delete_target_http_proxy(self, force=False):
        if force:
            name = self._ns_name(self.TARGET_PROXY_NAME)
        elif self.target_proxy:
            name = self.target_proxy.name
        else:
            return
        logger.info('Deleting HTTP Target proxy %s', name)
        self.compute.delete_target_http_proxy(name)
        self.target_proxy = None
        self.target_proxy_is_http = False

    def create_forwarding_rule(self, src_port: int):
        name = self._ns_name(self.FORWARDING_RULE_NAME)
        src_port = int(src_port)
        logging.info('Creating forwarding rule %s 0.0.0.0:%s -> %s in %s',
                     name, src_port, self.target_proxy.url, self.network)
        resource = self.compute.create_forwarding_rule(
            name, src_port, self.target_proxy, self.network_url)
        self.forwarding_rule = resource
        return resource

    def delete_forwarding_rule(self, force=False):
        if force:
            name = self._ns_name(self.FORWARDING_RULE_NAME)
        elif self.forwarding_rule:
            name = self.forwarding_rule.name
        else:
            return
        logger.info('Deleting Forwarding rule %s', name)
        self.compute.delete_forwarding_rule(name)
        self.forwarding_rule = None
