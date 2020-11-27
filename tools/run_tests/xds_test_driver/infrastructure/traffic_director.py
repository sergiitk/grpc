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
from typing import List, Optional

from googleapiclient import errors as google_api_errors

from infrastructure import gcp

HealthCheckProtocol = gcp.ComputeV1.HealthCheckProtocol
BackendServiceProtocol = gcp.ComputeV1.BackendServiceProtocol


class TrafficDirectorState:
    backends: List[gcp.GcpResource]
    backend_service: gcp.GcpResource
    health_check: gcp.GcpResource
    url_map: gcp.GcpResource
    target_proxy: gcp.GcpResource
    forwarding_rule: gcp.GcpResource

    def __init__(self,
                 backend_service: gcp.GcpResource,
                 health_check: gcp.GcpResource,
                 url_map: gcp.GcpResource,
                 target_proxy: gcp.GcpResource,
                 forwarding_rule: gcp.GcpResource,
                 backends: Optional[List[gcp.ZonalGcpResource]] = None):
        self.backend_service = backend_service
        self.health_check = health_check
        self.url_map = url_map
        self.target_proxy = target_proxy
        self.forwarding_rule = forwarding_rule
        self.backends = backends


class TrafficDirectorManager:
    def __init__(self, gcloud: gcp.GCloud, network_name='default'):
        # self.gcloud: gcp.GCloud = gcloud
        self.compute: gcp.ComputeV1 = gcloud.compute

        # Settings
        self.network_name: str = network_name

        # Mutable state
        self.health_check: Optional[gcp.GcpResource] = None
        self.backend_service: Optional[gcp.GcpResource] = None

    @property
    def network_url(self):
        return f'global/networks/{self.network_name}'

    def cleanup(self):
        # todo(sergiitk): continue on errors
        # Cleanup in the order of dependencies
        self.delete_backend_service()
        self.delete_health_check()

    def create(self):
        self.create_health_check()

    def create_health_check(self, name, protocol=HealthCheckProtocol.TCP):
        if self.health_check:
            raise ValueError('Health check %s already created, delete it first',
                             self.health_check.name)
        logging.info('Creating %s Health Check %s', protocol.name, name)
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
            logging.info('Deleting Health Check %s', name)
            self.compute.delete_health_check(name)
            self.health_check = None

    def create_backend_service(
        self,
        name: str,
        protocol: BackendServiceProtocol = BackendServiceProtocol.GRPC
    ) -> gcp.GcpResource:
        logging.info('Creating %s Backend Service %s', protocol.name, name)
        resource = self.compute.create_backend_service_traffic_director(
            name, health_check=self.health_check, protocol=protocol)
        self.backend_service = resource
        return resource

    def delete_backend_service(self, name=None):
        if name or self.backend_service:
            name = name or self.backend_service.name
            logging.info('Deleting Backend Service %s', name)
            self.compute.delete_backend_service(name)
            self.backend_service = None
#
#
# def setup_gke(
#     compute, project, network_url,
#     backend_service_name, health_check_name,
#     url_map_name, url_map_path_matcher_name,
#     target_proxy_name, forwarding_rule_name,
#     server_xds_host, server_xds_port
# ) -> TrafficDirectorState:
#     # Health check
#     try:
#         health_check = gcp.get_health_check(compute, project, health_check_name)
#         logging.info('Loaded TCP HealthCheck %s', health_check.name)
#     except google_api_errors.HttpError:
#         logging.info('Creating TCP HealthCheck %s', health_check_name)
#         health_check = gcp.create_tcp_health_check(compute, project,
#                                                    health_check_name)
#
#     # Global Backend Service (LB)
#     try:
#         backend_service = gcp.get_backend_service(
#             compute, project, backend_service_name)
#         logging.info('Loaded Backend Service %s', backend_service.name)
#     except google_api_errors.HttpError:
#         logging.info('Creating Backend Service %s', backend_service_name)
#         backend_service = gcp.create_backend_service(
#             compute, project, backend_service_name, health_check)
#
#     # URL map
#     server_xds_address = f'{server_xds_host}:{server_xds_port}'
#     try:
#         url_map = gcp.get_url_map(compute, project, url_map_name)
#         logging.info('Loaded URL Map %s', url_map.name)
#     except google_api_errors.HttpError:
#         logging.info('Creating URL map %s xds://%s -> %s',
#                      url_map_name,
#                      server_xds_address,
#                      backend_service.name)
#         url_map = gcp.create_url_map(compute, project,
#                                      url_map_name, url_map_path_matcher_name,
#                                      server_xds_address, backend_service)
#
#     # Target Proxy
#     try:
#         target_proxy = gcp.get_target_proxy(compute, project,
#                                             target_proxy_name)
#         logging.info('Loaded target proxy %s', target_proxy.name)
#     except google_api_errors.HttpError:
#         logging.info('Creating target proxy %s to url map %s',
#                      target_proxy_name, url_map.url)
#         target_proxy = gcp.create_target_proxy(
#             compute, project,
#             target_proxy_name, url_map)
#
#     # Global Forwarding Rule
#     try:
#         forwarding_rule = gcp.get_forwarding_rule(compute, project,
#                                                   forwarding_rule_name)
#         logging.info('Loaded forwarding rule %s', forwarding_rule.name)
#     except google_api_errors.HttpError:
#         logging.info('Creating forwarding rule %s 0.0.0.0:%s -> %s in %s',
#                      forwarding_rule_name, server_xds_port,
#                      target_proxy.url, network_url)
#         forwarding_rule = gcp.create_forwarding_rule(
#             compute, project,
#             forwarding_rule_name, server_xds_port,
#             target_proxy, network_url)
#
#     return TrafficDirectorState(backend_service, health_check,
#                                 url_map, target_proxy, forwarding_rule)
