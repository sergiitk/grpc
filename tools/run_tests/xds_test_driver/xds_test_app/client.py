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
    k8s_namespace: k8s.KubernetesNamespace
    deployment: Optional[k8s.V1Deployment]
    pod: Optional[k8s.V1Pod]

    def __init__(self,
                 k8s_namespace,
                 deployment_name,
                 *,
                 stats_port=8079,
                 network_name='default',
                 deployment_template='client.deployment.yaml',
                 use_port_forwarding=False):
        super().__init__(k8s_namespace)

        # Settings
        self.network_name = network_name
        self.deployment_name = deployment_name
        self.stats_port = stats_port
        self.deployment_template = deployment_template
        self.use_port_forwarding = use_port_forwarding

        # Mutable state
        self.deployment = None
        # Port forwarding kubernetes.stream.ws_client.PortForward
        self.pf = None

    def run(self, *, server_address, rpc, qps=10) -> XdsTestClient:
        # Reuse existing or create a new deployment
        self.deployment = self._reuse_deployment(self.deployment_name)
        if not self.deployment:
            self.deployment = self._create_deployment(
                self.deployment_template,
                deployment_name=self.deployment_name,
                namespace=self.k8s_namespace.name,
                stats_port=self.stats_port,
                network_name=self.network_name,
                server_address=server_address,
                rpc=rpc,
                qps=qps)

        self.deployment = self._get_deployment_with_available_replicas(
            self.deployment_name)

        # Load test client pod
        pods = self.k8s_namespace.list_deployment_pods(self.deployment)
        # We need only one client at the moment
        pod = self._get_pod_started(pods[0].metadata.name)

        # Experimental, for local debugging.
        if self.use_port_forwarding:
            logger.info('Enabling port forwarding from %s:%s',
                        pod.status.pod_ip, self.stats_port)
            local_ipv4 = '127.0.0.1'
            self.pf = self.k8s_namespace.port_forward_pod(
                pod, self.stats_port, local_address=local_ipv4)
            return XdsTestClient(host=local_ipv4, stats_port=self.stats_port)
        else:
            return XdsTestClient(host=pod.status.pod_ip,
                                 stats_port=self.stats_port)

    def cleanup(self):
        if self.pf:
            self.k8s_namespace.port_forward_stop(self.pf)
            self.pf = None
        if self.deployment:
            self._delete_deployment(self.deployment_name)
            self.deployment = None
