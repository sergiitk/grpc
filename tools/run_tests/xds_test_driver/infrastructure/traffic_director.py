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

import retrying

from infrastructure import gcp

logger = logging.getLogger(__name__)

# Type aliases
HealthCheckProtocol = gcp.ComputeV1.HealthCheckProtocol
BackendServiceProtocol = gcp.ComputeV1.BackendServiceProtocol


class TrafficDirectorManager:
    def __init__(self, gcloud: gcp.GCloud, network='default'):
        # self.gcloud: gcp.GCloud = gcloud
        self.compute: gcp.ComputeV1 = gcloud.compute

        # Settings
        self.network: str = network

        # Mutable state
        self.health_check: Optional[gcp.GcpResource] = None
        self.backend_service: Optional[gcp.GcpResource] = None
        self.url_map: Optional[gcp.GcpResource] = None
        self.target_proxy: Optional[gcp.GcpResource] = None
        self.forwarding_rule: Optional[gcp.GcpResource] = None
        self.backends = set()

    @property
    def network_url(self):
        return f'global/networks/{self.network}'

    def cleanup(self):
        # todo(sergiitk): continue on errors
        # Cleanup in the order of dependencies
        self.delete_forwarding_rule()
        self.delete_target_grpc_proxy()
        self.delete_url_map()
        self.delete_backend_service()
        self.delete_health_check()

    def create(self):
        # todo(sergiitk): finish
        pass

    def create_health_check(self, name, protocol=HealthCheckProtocol.TCP):
        if self.health_check:
            raise ValueError('Health check %s already created, delete it first',
                             self.health_check.name)
        logger.info('Creating %s Health Check %s', protocol.name, name)
        if protocol is HealthCheckProtocol.TCP:
            resource = self.compute.create_health_check_tcp(
                name, use_serving_port=True)
        else:
            raise ValueError('Unexpected protocol')

        self.health_check = resource
        return resource

    def delete_health_check(self, name=None):
        if name or self.health_check:
            name = name or self.health_check.name
            logger.info('Deleting Health Check %s', name)
            self.compute.delete_health_check(name)
            self.health_check = None

    def create_backend_service(
        self,
        name: str,
        protocol: BackendServiceProtocol = BackendServiceProtocol.GRPC
    ) -> gcp.GcpResource:
        logger.info('Creating %s Backend Service %s', protocol.name, name)
        resource = self.compute.create_backend_service_traffic_director(
            name, health_check=self.health_check, protocol=protocol)
        self.backend_service = resource
        return resource

    def delete_backend_service(self, name=None):
        if name or self.backend_service:
            name = name or self.backend_service.name
            logger.info('Deleting Backend Service %s', name)
            self.compute.delete_backend_service(name)
            self.backend_service = None

    def backend_service_add_backends(self):
        logging.info('Adding backends to Backend Service %s: %r',
                     self.backend_service.name, self.backends)
        self.compute.backend_service_add_backends(self.backend_service,
                                                  self.backends)

    def create_url_map(
        self,
        name: str,
        matcher_name,
        src_host,
        src_port,
    ) -> gcp.GcpResource:
        src_address = f'{src_host}:{src_port}'
        logger.info('Creating URL map %s %s -> %s',
                    name, src_address, self.backend_service.name)
        resource = self.compute.create_url_map(
            name, matcher_name, [src_address], self.backend_service)
        self.url_map = resource
        return resource

    def delete_url_map(self, name=None):
        if name or self.url_map:
            name = name or self.url_map.name
            logger.info('Deleting URL Map %s', name)
            self.compute.delete_url_map(name)
            self.url_map = None

    def create_target_grpc_proxy(self, name: str) -> gcp.GcpResource:
        # todo: different kinds
        logger.info('Creating target proxy %s to url map %s',
                    name, self.url_map.name)
        resource = self.compute.create_target_grpc_proxy(
            name, self.url_map)
        self.target_proxy = resource
        return resource

    def delete_target_grpc_proxy(self, name=None):
        # todo: different kinds
        if name or self.target_proxy:
            name = name or self.target_proxy.name
            logger.info('Deleting Target proxy %s', name)
            self.compute.delete_target_grpc_proxy(name)
            self.target_proxy = None

    def create_forwarding_rule(
        self,
        name: str,
        src_port: int,
    ) -> gcp.GcpResource:
        src_port = int(src_port)
        logging.info('Creating forwarding rule %s 0.0.0.0:%s -> %s in %s',
                     name, src_port, self.target_proxy.url, self.network)
        resource = self.compute.create_forwarding_rule(
            name, src_port, self.target_proxy, self.network_url)
        self.forwarding_rule = resource
        return resource

    def delete_forwarding_rule(self, name=None):
        if name or self.forwarding_rule:
            name = name or self.forwarding_rule.name
            logger.info('Deleting Forwarding rule %s', name)
            self.compute.delete_forwarding_rule(name)
            self.forwarding_rule = None

    def wait_for_backends_healthy_status(self):
        logger.debug(
            "Waiting for Backend Service %s to report all backends healthy %r",
            self.backend_service, self.backends)
        self.compute.wait_for_backends_healthy_status(
            self.backend_service, self.backends)
