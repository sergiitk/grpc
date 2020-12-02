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
from framework.infrastructure import k8s
from framework.infrastructure import gcp
from framework.infrastructure import traffic_director
from framework.test_app import client_app
from framework.test_app import server_app

logger = logging.getLogger(__name__)

# Type aliases
XdsTestServer = server_app.XdsTestServer
XdsTestClient = client_app.XdsTestClient


class XdsKubernetesTestCase(absltest.TestCase):
    k8s_api_manager: k8s.KubernetesApiManager
    gcp_api_manager: gcp.GcpApiManager

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        # GCP
        cls.project: str = xds_flags.PROJECT.value
        cls.network: str = xds_flags.NETWORK.value
        cls.gcp_service_account: str = xds_k8s_flags.GCP_SERVICE_ACCOUNT.value
        cls.td_bootstrap_image = xds_k8s_flags.TD_BOOTSTRAP_IMAGE.value

        # Base namespace
        # todo(sergiitk): generate for each test
        cls.namespace: str = xds_flags.NAMESPACE.value

        # Test server
        cls.server_image = xds_k8s_flags.SERVER_IMAGE.value
        cls.server_name = xds_flags.SERVER_NAME.value
        cls.server_port = xds_flags.SERVER_PORT.value
        cls.server_xds_host = xds_flags.SERVER_NAME.value
        cls.server_xds_port = xds_flags.SERVER_XDS_PORT.value

        # Test client
        cls.client_image = xds_k8s_flags.CLIENT_IMAGE.value
        cls.client_name = xds_flags.CLIENT_NAME.value
        cls.client_port_forwarding = xds_k8s_flags.CLIENT_PORT_FORWARDING.value

        # Resource managers
        cls.k8s_api_manager = k8s.KubernetesApiManager(
            xds_k8s_flags.KUBE_CONTEXT_NAME.value)
        cls.gcp_api_manager = gcp.GcpApiManager()

    def setUp(self):
        # Init this in child class
        self.server_runner = None
        self.client_runner = None
        self.td = None
        # todo(sergiitk): generate namespace with run id

    @classmethod
    def tearDownClass(cls):
        cls.k8s_api_manager.close()
        cls.gcp_api_manager.close()

    def tearDown(self):
        self.td.cleanup()
        self.client_runner.cleanup()
        self.server_runner.cleanup()

    def assertAllBackendsReceivedRpcs(self, stats_response):
        # todo(sergiitk): assert backends length
        logger.info(stats_response.rpcs_by_peer)
        for backend, rpcs_count in stats_response.rpcs_by_peer.items():
            self.assertGreater(
                int(rpcs_count), 0,
                msg='Backend {backend} did not receive a single RPC')

    def assertFailedRpcsAtMost(self, stats_response, count):
        self.assertLessEqual(int(stats_response.num_failures), count,
                             msg='Unexpected number of RPC failures '
                                 f'{stats_response.num_failures} > {count}')


class RegularXdsKubernetesTestCase(XdsKubernetesTestCase):
    def setUp(self):
        # Traffic Director Configuration
        self.td = traffic_director.TrafficDirectorManager(
            self.gcp_api_manager,
            project=self.project,
            resource_prefix=self.namespace,
            network=self.network)

        # Test Server Runner
        self.server_runner = server_app.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.namespace),
            deployment_name=self.server_name,
            image_name=self.server_image,
            gcp_service_account=self.gcp_service_account,
            network=self.network,
            td_bootstrap_image=self.td_bootstrap_image)

        # Test Client Runner
        self.client_runner = client_app.KubernetesClientRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.namespace),
            deployment_name=self.client_name,
            image_name=self.client_image,
            gcp_service_account=self.gcp_service_account,
            network=self.network,
            td_bootstrap_image=self.td_bootstrap_image,
            debug_use_port_forwarding=self.client_port_forwarding,
            reuse_namespace=True)

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

        logger.info('Fake waiting before adding backends to avoid error '
                    '400 RESOURCE_NOT_READY')
        # todo(sergiitk): figure out how to confirm NEG is ready to be added
        time.sleep(10)
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


class SecurityXdsKubernetesTestCase(XdsKubernetesTestCase):
    def setUp(self):
        # Traffic Director Configuration
        self.td = traffic_director.TrafficDirectorSecureManager(
            self.gcp_api_manager,
            project=self.project,
            resource_prefix=self.namespace,
            network=self.network)

        # Test Server Runner
        self.server_runner = server_app.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.namespace),
            deployment_name=self.server_name,
            image_name=self.server_image,
            gcp_service_account=self.gcp_service_account,
            network=self.network,
            deployment_template='server-secure.deployment.yaml',
            td_bootstrap_image=self.td_bootstrap_image)

        # Test Client Runner
        self.client_runner = client_app.KubernetesClientRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.namespace),
            deployment_name=self.client_name,
            image_name=self.client_image,
            gcp_service_account=self.gcp_service_account,
            network=self.network,
            td_bootstrap_image=self.td_bootstrap_image,
            debug_use_port_forwarding=self.client_port_forwarding,
            deployment_template='client-secure.deployment.yaml',
            reuse_namespace=True)

    def startSecureTestServer(self, replica_count=1, **kwargs) -> XdsTestServer:
        test_server = self.server_runner.run(
            replica_count=replica_count,
            test_port=self.server_port,
            maintenance_port="8081",
            secure_mode=True,
            **kwargs)
        test_server.xds_address = (self.server_xds_host, self.server_xds_port)
        return test_server

    def setupSecureXds(self):
        # Traffic Director
        self.td.setup_for_grpc(self.server_xds_host, self.server_xds_port)
        self.td.setup_server_security(self.server_port)
        self.td.setup_client_security(self.namespace, self.server_name)

    def setupServerBackends(self):
        # Load Backends
        neg_name, neg_zones = self.server_runner.k8s_namespace.get_service_neg(
            self.server_runner.service_name, self.server_port)

        logger.info('Fake waiting before adding backends to avoid error '
                    '400 RESOURCE_NOT_READY')
        # todo(sergiitk): figure out how to confirm NEG is ready to be added
        time.sleep(30)
        self.td.backend_service_add_neg_backends(neg_name, neg_zones)

        logger.info('Wait for xDS to stabilize')
        # todo(sergiitk): wait until client reports rpc health
        time.sleep(120)

    def startSecureTestClientForServer(
        self,
        test_server: XdsTestServer,
        **kwargs
    ) -> XdsTestClient:
        test_client = self.client_runner.run(
            server_address=test_server.xds_uri, **kwargs)
        return test_client
