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
from typing import Tuple

from framework.infrastructure import k8s
from framework.test_app import base_runner

logger = logging.getLogger(__name__)


class XdsTestServer:
    def __init__(self, *,
                 ip: str,
                 rpc_port: int,
                 secure_mode: Optional[bool] = False,
                 server_id: Optional[str] = None,
                 xds_host: Optional[str] = None,
                 xds_port: Optional[int] = None,
                 rpc_host: Optional[str] = None,
                 maintenance_port: Optional[int] = None):
        self.ip = ip
        self.rpc_port = rpc_port
        # Optional fields
        self.rpc_host = rpc_host or ip
        self.maintenance_port = maintenance_port or rpc_port
        self.xds_host = xds_host
        self.xds_port = xds_port
        self.secure_mode = secure_mode
        self.server_id = server_id

    @property
    def rpc_address(self) -> str:
        return f'{self.rpc_host}:{self.rpc_port}'

    @property
    def maintenance_rpc_address(self) -> str:
        return f'{self.rpc_host}:{self.maintenance_port}'

    def set_xds_address(self, xds_host, xds_port: Optional[int] = None):
        self.xds_host = xds_host
        self.xds_port = xds_port

    @property
    def xds_address(self) -> str:
        if not self.xds_host:
            return ''
        if not self.xds_port:
            return self.xds_host

        return f'{self.xds_host}:{self.xds_port}'

    @property
    def xds_uri(self) -> str:
        if not self.xds_host:
            return ''
        return f'xds:///{self.xds_address}'


class ServerRunError(Exception):
    """Error running Test Server"""


class KubernetesServerRunner(base_runner.KubernetesBaseRunner):
    def __init__(self,
                 k8s_namespace,
                 *,
                 deployment_name,
                 image_name,
                 gcp_service_account,
                 service_account_name=None,
                 service_name=None,
                 neg_name=None,
                 td_bootstrap_image=None,
                 network='default',
                 deployment_template='server.deployment.yaml',
                 service_account_template='service-account.yaml',
                 service_template='server.service.yaml',
                 reuse_service=False,
                 reuse_namespace=False,
                 namespace_template=None):
        super().__init__(k8s_namespace, namespace_template, reuse_namespace)

        # Settings
        self.deployment_name = deployment_name
        self.image_name = image_name
        self.gcp_service_account = gcp_service_account
        self.service_account_name = service_account_name or deployment_name
        self.service_name = service_name or deployment_name
        # xDS bootstrap generator
        self.td_bootstrap_image = td_bootstrap_image
        # This only works in k8s >= 1.18.10-gke.600
        # https://cloud.google.com/kubernetes-engine/docs/how-to/standalone-neg#naming_negs
        self.neg_name = neg_name or (f'{self.k8s_namespace.name}-'
                                     f'{self.service_name}')
        self.network = network
        self.deployment_template = deployment_template
        self.service_account_template = service_account_template
        self.service_template = service_template
        self.reuse_service = reuse_service

        # Mutable state
        self.deployment: Optional[k8s.V1Deployment] = None
        self.service_account: Optional[k8s.V1ServiceAccount] = None
        self.service: Optional[k8s.V1Service] = None

    def run(self, *,
            test_port=8080, maintenance_port=8080,
            secure_mode=False, server_id=None,
            replica_count=1) -> XdsTestServer:
        super().run()

        # Create service account
        self.service_account = self._create_service_account(
            self.service_account_template,
            service_account_name=self.service_account_name,
            namespace_name=self.k8s_namespace.name,
            gcp_service_account=self.gcp_service_account)

        # Always create a new deployment
        self.deployment = self._create_deployment(
            self.deployment_template,
            deployment_name=self.deployment_name,
            image_name=self.image_name,
            namespace_name=self.k8s_namespace.name,
            service_account_name=self.service_account_name,
            td_bootstrap_image=self.td_bootstrap_image,
            network_name=self.network,
            replica_count=replica_count,
            test_port=test_port,
            maintenance_port=maintenance_port,
            server_id=server_id,
            secure_mode=secure_mode)

        self._wait_deployment_with_available_replicas(
            self.deployment_name, replica_count, timeout_sec=120)

        # Wait for pods running
        pods = self.k8s_namespace.list_deployment_pods(self.deployment)
        for pod in pods:
            self._wait_pod_started(pod.metadata.name)

        # Reuse existing if requested, create a new deployment when missing.
        # Useful for debugging to avoid NEG loosing relation to deleted service.
        if self.reuse_service:
            self.service = self._reuse_service(self.service_name)
        if not self.service:
            self.service = self._create_service(
                self.service_template,
                service_name=self.service_name,
                namespace_name=self.k8s_namespace.name,
                deployment_name=self.deployment_name,
                neg_name=self.neg_name,
                test_port=test_port,
                # todo(sergiitk): expose maintenance_port via service
                maintenance_port=maintenance_port)

        self._wait_service_neg(self.service_name, test_port)
        return XdsTestServer(
            # todo(sergiitk): resolve ip
            ip=None,
            rpc_port=test_port,
            secure_mode=secure_mode,
            server_id=server_id)

    def cleanup(self, *, force=False, force_namespace=False):
        if self.deployment or force:
            self._delete_deployment(self.deployment_name)
            self.deployment = None
        if (self.service and not self.reuse_service) or force:
            self._delete_service(self.service_name)
            self.service = None
        if self.service_account or force:
            self._delete_service_account(self.service_account_name)
            self.service_account = None
        super().cleanup(force=(force_namespace and force))
