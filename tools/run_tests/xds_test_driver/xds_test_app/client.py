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

import grpc
import yaml

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


class ClientRunError(Exception):
    """Error running Test Client"""


class KubernetesClientRunner:
    deployment: Optional[k8s.client.V1Deployment]
    pod: Optional[k8s.client.V1Pod]

    def __init__(self,
                 k8s_context_name,
                 k8s_client,
                 namespace,
                 deployment_name,
                 stats_port=8079,
                 template_name='client.deployment.yaml',
                 use_port_forwarding=False):
        self.k8s_context_name = k8s_context_name
        self.k8s_client = k8s_client
        self.namespace = namespace
        self.deployment_name = deployment_name
        self.stats_port = stats_port
        self.template_name = template_name
        self.use_port_forwarding = use_port_forwarding
        self.deployment = None
        self.pod = None
        # Port forwarding kubernetes.stream.ws_client.PortForward
        self.pf = None

    def run(self) -> XdsTestClient:
        # Reuse existing or create a new deployment
        self.deployment = self._reuse_deployment() or self._create_deployment()
        self._wait_for_deployment_available()

        # Load test client pod
        self.pod = self._get_pod()
        self._wait_for_pod_started()

        if self.use_port_forwarding:
            logger.info('Enabling port forwarding from %s:%s',
                        self.pod.status.pod_ip, self.stats_port)

            host = '127.0.0.1'
            self.pf = k8s.port_forward(self.k8s_context_name, self.namespace,
                                       self.pod, self.stats_port,
                                       local_address=host)
            return XdsTestClient(host=host, stats_port=self.stats_port)
        else:
            return XdsTestClient(host=self.pod.status.pod_ip,
                                 stats_port=self.stats_port)

    def cleanup(self):
        if self.pf:
            k8s.port_forward_shutdown(self.pf)
        if self.deployment:
            self._delete_deployment()

    def _create_deployment(self) -> k8s.client.V1Deployment:
        yaml_file = self._template_file_from_name(self.template_name)
        logger.info("Creating client from: %s", yaml_file)
        manifests = self._manifests_from_yaml_file(yaml_file)
        # Load the first document
        # todo(sergiitk): index by type?
        manifest = next(manifests)
        # Error out on multi-document yaml
        if next(manifests, False):
            raise ClientRunError(
                f'Exactly one document expected in client manifest {yaml_file}')

        # Apply the manifest
        k8s_objects = k8s.apply_manifest(self.k8s_client, manifest,
                                         self.namespace)
        # Check correctness
        if len(k8s_objects) != 1 or not isinstance(k8s_objects[0],
                                                   k8s.client.V1Deployment):
            raise ClientRunError('Expected exactly one Deployment created from '
                                 f'manifest {yaml_file}')

        deployment: k8s.client.V1Deployment = k8s_objects[0]
        if deployment.metadata.name != self.deployment_name:
            raise ClientRunError(
                'Client Deployment created with unexpected name: '
                f'{deployment.metadata.name}')
        logger.info('Deployment %s created at %s',
                    deployment.metadata.self_link,
                    deployment.metadata.creation_timestamp)

        return deployment

    def _reuse_deployment(self):
        deployment = k8s.get_deployment_by_name(self.k8s_client, self.namespace,
                                                self.deployment_name)
        # todo(sergiitk): check if good or must be recreated
        return deployment

    def _delete_deployment(self):
        deployment_name = self.deployment.metadata.name
        k8s.delete_deployment(self.k8s_client, self.namespace, deployment_name)
        logger.info('Deployment %s deleted', deployment_name)
        self.deployment = None

    def _wait_for_deployment_available(self, save_latest_state=False):
        deployment = k8s.wait_for_deployment_minimum_replicas_available(
            self.k8s_client, self.namespace, self.deployment)
        logger.info('Deployment %s has %i replicas available',
                    deployment.metadata.name,
                    deployment.status.available_replicas)
        # Use the most recent deployment state
        if save_latest_state:
            self.deployment = deployment

    def _wait_for_pod_started(self, save_latest_state=True):
        pod = k8s.wait_for_started_pod(self.k8s_client, self.namespace,
                                       self.pod)
        logger.info('Pod %s ready, IP: %s', pod.metadata.name,
                    pod.status.pod_ip)
        if save_latest_state:
            self.pod = pod

    def _get_pod(self) -> k8s.client.V1Pod:
        pods = k8s.get_deployment_pods(self.k8s_client, self.namespace,
                                       self.deployment)
        # We need only one client at the moment
        return pods[0]

    @staticmethod
    def _manifests_from_yaml_file(yaml_file):
        # Parse yaml
        with open(yaml_file) as f:
            with contextlib.closing(yaml.safe_load_all(f)) as yml:
                for manifest in yml:
                    yield manifest

    @staticmethod
    def _template_file_from_name(template_name):
        templates_path = pathlib.Path(__file__).parent / '../templates'
        return templates_path.joinpath(template_name).absolute()
