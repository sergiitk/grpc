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

import grpc

from xds_test_app import base_runner
from infrastructure import k8s
from src.proto.grpc.testing import test_pb2_grpc
from src.proto.grpc.testing import messages_pb2

logger = logging.getLogger()


class XdsTestClient:
    DEFAULT_STATS_REQUEST_TIMEOUT_SEC = 1200
    CONNECTION_TIMEOUT_SEC = 60

    def __init__(self, host: str, stats_port: Tuple[int, str]):
        self.host = host
        self.stats_service_port = int(stats_port)

    @property
    def stats_service_address(self) -> str:
        return f'{self.host}:{self.stats_service_port}'

    def request_load_balancer_stats(self, num_rpcs, timeout_sec=None):
        if timeout_sec is None:
            timeout_sec = self.DEFAULT_STATS_REQUEST_TIMEOUT_SEC
        request_timeout = timeout_sec + self.CONNECTION_TIMEOUT_SEC

        with grpc.insecure_channel(self.stats_service_address) as channel:
            logger.info('Invoking GetClientStats RPC on %s',
                        self.stats_service_address)

            stub = test_pb2_grpc.LoadBalancerStatsServiceStub(channel)
            stats_request = messages_pb2.LoadBalancerStatsRequest(
                num_rpcs=num_rpcs, timeout_sec=timeout_sec)
            response = stub.GetClientStats(stats_request,
                                           wait_for_ready=True,
                                           timeout=request_timeout)

            logger.debug('Invoked GetClientStats RPC to %s: %s',
                         self.stats_service_address, response)
            return response


class KubernetesClientRunner(base_runner.KubernetesBaseRunner):
    def __init__(self,
                 k8s_namespace,
                 deployment_name,
                 gcp_service_account,
                 *,
                 service_account_name=None,
                 stats_port=8079,
                 td_bootstrap_image=None,
                 network='default',
                 deployment_template='client.deployment.yaml',
                 service_account_template='service-account.yaml',
                 reuse_namespace=False,
                 namespace_template=None,
                 debug_use_port_forwarding=False):
        super().__init__(k8s_namespace, namespace_template, reuse_namespace)

        # Settings
        self.deployment_name = deployment_name
        self.gcp_service_account = gcp_service_account
        self.service_account_name = service_account_name or deployment_name
        self.stats_port = stats_port
        # xDS bootstrap generator
        self.td_bootstrap_image = td_bootstrap_image
        self.network = network
        self.deployment_template = deployment_template
        self.service_account_template = service_account_template
        self.debug_use_port_forwarding = debug_use_port_forwarding

        # Mutable state
        self.deployment: Optional[k8s.V1Deployment] = None
        self.service_account: Optional[k8s.V1ServiceAccount] = None
        self.port_forwarder = None

    def run(self, *,
            server_address,
            rpc='UnaryCall', qps=25,
            secure_mode=False) -> XdsTestClient:
        super().run()
        # todo(sergiitk): make rpc UnaryCall enum or get it from proto

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
            service_account_name=self.service_account_name,
            namespace_name=self.k8s_namespace.name,
            stats_port=self.stats_port,
            network_name=self.network,
            server_address=server_address,
            rpc=rpc,
            qps=qps,
            td_bootstrap_image=self.td_bootstrap_image,
            secure_mode=secure_mode)

        self._wait_deployment_with_available_replicas(self.deployment_name)

        # Load test client pod. We need only one client at the moment
        pod = self.k8s_namespace.list_deployment_pods(self.deployment)[0]
        self._wait_pod_started(pod.metadata.name)
        client_host: str = pod.status.pod_ip

        # Experimental, for local debugging.
        if self.debug_use_port_forwarding:
            logger.info('Enabling port forwarding from %s:%s',
                        client_host, self.stats_port)
            self.port_forwarder = self.k8s_namespace.port_forward_pod(
                pod, remote_port=self.stats_port)
            client_host = self.k8s_namespace.PORT_FORWARD_LOCAL_ADDRESS

        return XdsTestClient(host=client_host,
                             stats_port=self.stats_port)

    def cleanup(self, *, force=False, force_namespace=False):
        if self.port_forwarder:
            self.k8s_namespace.port_forward_stop(self.port_forwarder)
            self.port_forwarder = None
        if self.deployment or force:
            self._delete_deployment(self.deployment_name)
            self.deployment = None
        if self.service_account or force:
            self._delete_service_account(self.service_account_name)
            self.service_account = None
        super().cleanup(force=force_namespace and force)
