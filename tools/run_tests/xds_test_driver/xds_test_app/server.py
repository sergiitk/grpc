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

import contextlib
import logging
import pathlib
from typing import Optional
from typing import Tuple

from mako import template
import grpc
import yaml

from infrastructure import k8s
from src.proto.grpc.testing import test_pb2_grpc
from src.proto.grpc.testing import messages_pb2
from xds_test_app import base_runner

logger = logging.getLogger()


class XdsTestServer:
    def __init__(
        self,
        port,
        maintenance_port,
        secure_mode: Optional[bool] = False,
        server_id: Optional[str] = None
    ):
        self.server_id = server_id
        self.port = port
        self.maintenance_port = maintenance_port
        self.secure_mode = secure_mode
        self.xds_host = None
        self.xds_port = None

    @property
    def xds_address(self) -> str:
        if not self.xds_host:
            return ''
        return f'{self.xds_host}:f{self.xds_port}'

    @xds_address.setter
    def xds_address(self, tuple_address: Tuple[str, int]):
        self.xds_host = tuple_address[0]
        self.xds_port = tuple_address[1]

    @property
    def xds_uri(self) -> str:
        if not self.xds_host:
            return ''
        return f'xds:///{self.xds_address}'


class ServerRunError(Exception):
    """Error running Test Server"""


class KubernetesServerRunner(base_runner.KubernetesBaseRunner):
    k8s_namespace: k8s.KubernetesNamespace
    deployment: Optional[k8s.V1Deployment]

    def __init__(self,
                 k8s_namespace,
                 deployment_name,
                 *,
                 service_name=None,
                 network_name='default',
                 deployment_template='server.deployment.yaml',
                 service_template='server.service.yaml'):
        super().__init__(k8s_namespace)

        # Settings
        self.deployment_name = deployment_name
        self.service_name = service_name or deployment_name
        self.deployment_template = deployment_template
        self.service_template = service_template
        self.network_name = network_name
        # todo(sergiitk): make adjustable
        self.replica_count = 2

        # Mutable state
        self.service = None
        self.deployment = None

    def run(self, *,
            port=8080, maintenance_port=8080,
            secure_mode=False, server_id=None) -> XdsTestServer:
        # Reuse existing or create a new deployment
        self.deployment = self._create_deployment(
            self.deployment_template,
            deployment_name=self.deployment_name,
            service_name=self.service_name,
            namespace=self.k8s_namespace.name,
            network_name=self.network_name,
            replica_count=self.replica_count,
            port=port,
            maintenance_port=maintenance_port,
            secure_mode=secure_mode,
            server_id=server_id)

        self._get_deployment_with_available_replicas(
            self.deployment_name, self.replica_count, timeout_sec=120)

        self.service = self._create_service(
            self.service_template,
            service_name=self.service_name,
            deployment_name=self.deployment_name,
            namespace=self.k8s_namespace.name,
            port=port,
            maintenance_port=maintenance_port,
            secure_mode=secure_mode)

        return XdsTestServer(port, maintenance_port, secure_mode, server_id)

    def cleanup(self):
        if self.deployment:
            self._delete_deployment(self.deployment_name)
            self.deployment = None
        if self.service:
            self._delete_service(self.service_name)
            self.service = None
