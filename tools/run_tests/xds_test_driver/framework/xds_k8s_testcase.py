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

from absl.testing import absltest

from framework import xds_flags
from framework import xds_k8s_flags
from infrastructure import k8s
from infrastructure import gcp
from infrastructure import traffic_director
import xds_test_app.client
import xds_test_app.server

logger = logging.getLogger(__name__)

# Type aliases
XdsTestServer = xds_test_app.server.XdsTestServer
XdsTestClient = xds_test_app.client.XdsTestClient


class XdsKubernetesTestCase(absltest.TestCase):
    k8s_api_manager: k8s.KubernetesApiManager
    gcp_api_manager: gcp.GcpApiManager

    @classmethod
    def setUpClass(cls):
        # GCP
        cls.project: str = xds_flags.PROJECT.value
        cls.network: str = xds_flags.NETWORK.value
        cls.gcp_service_account: str = xds_k8s_flags.GCP_SERVICE_ACCOUNT.value

        # Base namespace
        # todo(sergiitk): generate for each test
        cls.namespace: str = xds_flags.NAMESPACE.value

        # todo(sergiitk): move to args
        # Test app
        cls.server_name = xds_flags.SERVER_NAME.value
        cls.server_port = xds_flags.SERVER_PORT.value
        cls.server_xds_host = xds_flags.SERVER_NAME.value
        cls.server_xds_port = xds_flags.SERVER_XDS_PORT.value
        cls.client_name = xds_flags.CLIENT_NAME.value
        cls.client_port_forwarding = xds_k8s_flags.CLIENT_PORT_FORWARDING.value

        # Shared services
        cls.k8s_api_manager = k8s.KubernetesApiManager(
            xds_k8s_flags.KUBE_CONTEXT_NAME.value)
        cls.gcp_api_manager = gcp.GcpApiManager()

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
            self.gcp_api_manager,
            project=self.project,
            resource_prefix=namespace,
            network=self.network)

        # Test Server Runner
        self.server_runner = xds_test_app.server.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, server_namespace),
            gcp_service_account=self.gcp_service_account,
            deployment_name=self.server_name,
            network=self.network)

        # Test Client Runner
        self.client_runner = xds_test_app.client.KubernetesClientRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, client_namespace),
            self.client_name,
            gcp_service_account=self.gcp_service_account,
            network=self.network,
            debug_use_port_forwarding=self.client_port_forwarding,
            reuse_namespace=True)

    def tearDown(self):
        logger.debug('######## tearDown(): resource cleanup initiated ########')
        self.td.cleanup()
        self.client_runner.cleanup()
        self.server_runner.cleanup()

    def startTestServer(self, replica_count=1, **kwargs) -> XdsTestServer:
        test_server = self.server_runner.run(
            replica_count=replica_count,
            test_port=self.server_port,
            **kwargs)
        test_server.xds_address = (self.server_xds_host, self.server_xds_port)
        return test_server

    def setupXdsForServer(self, test_server: XdsTestServer):
        # Traffic Director
        self.td.setup_for_grpc(test_server.xds_host, test_server.xds_port)

        # Load Backends
        neg_name, neg_zones = self.server_runner.k8s_namespace.get_service_neg(
            self.server_runner.service_name, test_server.port)

        self.td.backend_service_add_neg_backends(neg_name, neg_zones)

        logger.info('Wait for xDS to stabilize')
        # todo(sergiitk): wait until client reports rpc health
        time.sleep(120)

    def startTestClientForServer(
        self,
        test_server: XdsTestServer,
        **kwargs
    ) -> XdsTestClient:
        test_client = self.client_runner.run(
            server_address=test_server.xds_uri, **kwargs)
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
