#  Copyright 2020 gRPC authors.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import logging
import time
from typing import Optional

from absl.testing import absltest
from absl import flags

from infrastructure import k8s
from infrastructure import gcp
from infrastructure import traffic_director
import xds_test_app.client
import xds_test_app.server

logger = logging.getLogger(__name__)
# Flags
_PROJECT = flags.DEFINE_string(
    "project", default=None, help="GCP Project ID, required")
_NAMESPACE = flags.DEFINE_string(
    "namespace", default=None,
    help="Isolate GCP resources using given namespace / name prefix")
_KUBE_CONTEXT_NAME = flags.DEFINE_string(
    "kube_context_name", default=None, help="Kubectl context to use")
_GCP_SERVICE_ACCOUNT = flags.DEFINE_string(
    "gcp_service_account", default=None,
    help="GCP Service account for GKE workloads to impersonate")
_NETWORK = flags.DEFINE_string(
    "network", default="default", help="GCP Network ID")
_CLIENT_PORT_FORWARDING = flags.DEFINE_bool(
    "client_debug_use_port_forwarding", default=False,
    help="Development only: use kubectl port-forward to connect to test client")
flags.mark_flags_as_required([
    "project",
    "namespace",
    "gcp_service_account",
    "kube_context_name"
])
# Type aliases
XdsTestServer = xds_test_app.server.XdsTestServer
XdsTestClient = xds_test_app.client.XdsTestClient


class XdsKubernetesTestCase(absltest.TestCase):
    k8s_api_manager: Optional[k8s.KubernetesApiManager] = None
    gcp_api_manager: Optional[gcp.GcpApiManager] = None
    CLIENT_NAME = 'psm-grpc-client'
    SERVER_NAME = 'psm-grpc-server'
    SERVER_XDS_HOST = 'xds-test-server'
    SERVER_XDS_PORT = 8000

    @classmethod
    def setUpClass(cls):
        # GCP
        cls.project: str = _PROJECT.value
        cls.network: str = _NETWORK.value

        # Base namespace
        # todo(sergiitk): generate for each test
        cls.namespace: str = _NAMESPACE.value

        # todo(sergiitk): move to args
        # Client
        cls.client_debug_use_port_forwarding = _CLIENT_PORT_FORWARDING.value

        # Shared services
        cls.k8s_api_manager = k8s.KubernetesApiManager(_KUBE_CONTEXT_NAME.value)
        cls.gcp_api_manager = gcp.GcpApiManager()
        cls.gcloud = gcp.GCloud(cls.gcp_api_manager, cls.project)
        cls.compute = cls.gcloud.compute

    @classmethod
    def tearDownClass(cls):
        cls.k8s_api_manager.close()
        cls.gcp_api_manager.close()

    def setUp(self):
        # todo(sergiitk): generate with run id
        namespace = self.namespace
        client_namespace = self.namespace
        server_namespace = self.namespace

        # Traffic Director Configuration
        self.td = traffic_director.TrafficDirectorManager(
            self.gcloud, network=self.network, namespace=namespace)

        # Test Server Runner
        self.server_runner = xds_test_app.server.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, server_namespace),
            gcp_service_account=_GCP_SERVICE_ACCOUNT.value,
            deployment_name=self.SERVER_NAME,
            network=self.network)

        # Test Client Runner
        self.client_runner = xds_test_app.client.KubernetesClientRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, client_namespace),
            self.CLIENT_NAME,
            gcp_service_account=_GCP_SERVICE_ACCOUNT.value,
            network=self.network,
            debug_use_port_forwarding=self.client_debug_use_port_forwarding,
            reuse_namespace=True)

    def tearDown(self):
        logger.debug('######## tearDown(): resource cleanup initiated ########')
        self.td.cleanup()
        self.client_runner.cleanup()
        self.server_runner.cleanup()

    def startTestServer(self, replica_count) -> XdsTestServer:
        test_server = self.server_runner.run(replica_count=replica_count)
        test_server.xds_address = (self.SERVER_XDS_HOST, self.SERVER_XDS_PORT)
        return test_server

    def setupXdsForServer(self, test_server: XdsTestServer):
        # Traffic Director
        self.td.setup_for_grpc(test_server.xds_host, test_server.xds_port)

        # Load Backends
        neg_name, neg_zones = self.server_runner.k8s_namespace.get_service_neg(
            self.server_runner.service_name, test_server.port)

        logger.info('Loading NEGs')
        for neg_zone in neg_zones:
            backend = self.compute.wait_for_network_endpoint_group(
                neg_name, neg_zone)
            self.td.backends.add(backend)

        logger.info('Fake waiting before adding backends to avoid error '
                    '400 RESOURCE_NOT_READY')
        # todo(sergiitk): figure out how to confirm NEG is ready to be added
        time.sleep(10)
        self.td.backend_service_add_backends()
        self.td.wait_for_backends_healthy_status()

        # todo(sergiitk): wait until client reports rpc health
        logger.info('Wait for xDS to stabilize')
        time.sleep(90)

    def startTestClientForServer(
        self,
        test_server: XdsTestServer
    ) -> XdsTestClient:
        # todo(sergiitk): make rpc UnaryCall enum or get it from proto
        test_client = self.client_runner.run(server_address=test_server.xds_uri)
        return test_client

    def assertAllBackendsReceivedRpcs(self, stats_response):
        # todo(sergiitk): assert backends length
        logger.info(stats_response.rpcs_by_peer)
        for backend, rpcs_count in stats_response.rpcs_by_peer.items():
            with self.subTest(f'Backend {backend} received RPCs'):
                self.assertGreater(int(rpcs_count), 0,
                                   msg='Did not receive a single RPC')

    def assertFailedRpcsAtMost(self, stats_response, count):
        self.assertLessEqual(int(stats_response.num_failures), count,
                             msg='Unexpected number of RPC failures '
                                 f'{stats_response.num_failures} > {count}')
