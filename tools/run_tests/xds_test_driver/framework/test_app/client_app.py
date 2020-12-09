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
from grpc_channelz.v1 import channelz_pb2
from grpc_channelz.v1 import channelz_pb2_grpc

from framework.test_app import base_runner
from framework.test_app import grpc_helper
from framework.test_app import channelz_helper
from framework.infrastructure import k8s
from src.proto.grpc.testing import test_pb2_grpc
from src.proto.grpc.testing import messages_pb2

logger = logging.getLogger(__name__)

# Type aliases
LoadBalancerStatsRequest = messages_pb2.LoadBalancerStatsRequest
LoadBalancerStatsResponse = messages_pb2.LoadBalancerStatsResponse


class XdsTestClient:
    DEFAULT_STATS_REQUEST_TIMEOUT_SEC = 1200

    def __init__(self, *,
                 ip: str,
                 port: Tuple[int, str],
                 server_address: str,
                 rpc_host: Optional[str] = None):
        self.host = ip
        self.server_address = server_address
        self.rpc_port = int(port)
        self.rpc_host = rpc_host or ip
        self._channel: Optional[grpc.Channel] = None

    @property
    def rpc_address(self) -> str:
        return f'{self.rpc_host}:{self.rpc_port}'

    def connect(self):
        if not self._channel:
            self._channel = grpc.insecure_channel(self.rpc_address)

    def close(self):
        if self._channel:
            self._channel.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()

    def request_load_balancer_stats(
        self, *,
        num_rpcs,
        partial_results_timeout_sec: Optional[int] = None
    ) -> LoadBalancerStatsResponse:
        stub = test_pb2_grpc.LoadBalancerStatsServiceStub(self._channel)
        if partial_results_timeout_sec is None:
            partial_results_timeout_sec = self.DEFAULT_STATS_REQUEST_TIMEOUT_SEC

        logger.info('Invoking GetClientStats RPC on %s', self.rpc_address)
        stats_request = LoadBalancerStatsRequest(
            num_rpcs=num_rpcs, timeout_sec=partial_results_timeout_sec)

        total_timeout_sec = grpc_helper.GRPC_DEFAULT_TIMEOUT_SEC + partial_results_timeout_sec
        response = grpc_helper.call_unary_when_ready(
            method=stub.GetClientStats,
            request=stats_request,
            timeout_sec=total_timeout_sec
        )


        with grpc.insecure_channel(self.rpc_address) as channel:




            response = stub.GetClientStats(stats_request,
                                           wait_for_ready=True,
                                           timeout=request_timeout)

            logger.debug('Invoked GetClientStats RPC to %s: %s',
                         self.rpc_address, response)
            return response

    def get_server_channel(self):
        return channelz_helper.get_channel_with_target(self._channel,
                                                       self.server_address)




class KubernetesClientRunner(base_runner.KubernetesBaseRunner):
    def __init__(self,
                 k8s_namespace,
                 *,
                 deployment_name,
                 image_name,
                 gcp_service_account,
                 td_bootstrap_image,
                 service_account_name=None,
                 stats_port=8079,
                 network='default',
                 deployment_template='client.deployment.yaml',
                 service_account_template='service-account.yaml',
                 reuse_namespace=False,
                 namespace_template=None,
                 debug_use_port_forwarding=False):
        super().__init__(k8s_namespace, namespace_template, reuse_namespace)

        # Settings
        self.deployment_name = deployment_name
        self.image_name = image_name
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
            secure_mode=False,
            print_response=False) -> XdsTestClient:
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
            image_name=self.image_name,
            namespace_name=self.k8s_namespace.name,
            service_account_name=self.service_account_name,
            td_bootstrap_image=self.td_bootstrap_image,
            network_name=self.network,
            stats_port=self.stats_port,
            server_address=server_address,
            rpc=rpc,
            qps=qps,
            secure_mode=secure_mode,
            print_response=print_response)

        self._wait_deployment_with_available_replicas(self.deployment_name)

        # Load test client pod. We need only one client at the moment
        pod = self.k8s_namespace.list_deployment_pods(self.deployment)[0]
        self._wait_pod_started(pod.metadata.name)
        pod_ip = pod.status.pod_ip
        rpc_host = None

        # Experimental, for local debugging.
        if self.debug_use_port_forwarding:
            logger.info('Enabling port forwarding from %s:%s',
                        pod_ip, self.stats_port)
            self.port_forwarder = self.k8s_namespace.port_forward_pod(
                pod, remote_port=self.stats_port)
            rpc_host = self.k8s_namespace.PORT_FORWARD_LOCAL_ADDRESS

        return XdsTestClient(ip=pod_ip,
                             port=self.stats_port,
                             server_address=server_address,
                             rpc_host=rpc_host)

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
