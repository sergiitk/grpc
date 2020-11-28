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
import os
import time

from absl.testing import absltest
import dotenv

from infrastructure import k8s
from infrastructure import gcp
from infrastructure import traffic_director
import xds_test_app.client
import xds_test_app.server

logger = logging.getLogger(__name__)


class BaselineTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls):
        # todo(sergiitk): move to args
        dotenv.load_dotenv()
        # GCP
        cls.project: str = os.environ['PROJECT_ID']
        cls.network: str = os.environ['NETWORK_NAME']

        # K8s
        cls.k8s_context_name = os.environ['KUBE_CONTEXT_NAME']
        cls.k8s_namespace = os.environ['NAMESPACE']

        # Client
        cls.client_name = os.environ['CLIENT_NAME']
        cls.client_debug_use_port_forwarding = bool(
            os.getenv('CLIENT_DEBUG_USE_PORT_FORWARDING', False))

        # Server
        cls.server_name = os.environ['SERVER_NAME']
        cls.server_test_port = os.environ['SERVER_TEST_PORT']
        cls.server_maintenance_port = os.environ['SERVER_MAINTENANCE_PORT']
        cls.server_replica_count = int(os.environ['SERVER_REPLICA_COUNT'])
        cls.server_debug_reuse_service = bool(
            os.getenv('SERVER_DEBUG_REUSE_SERVICE', False))

        # Server xDS settings
        cls.server_xds_host = os.environ['SERVER_XDS_HOST']
        cls.server_xds_port = os.environ['SERVER_XDS_PORT']

        # Backend service (Traffic Director)
        cls.backend_service_name = os.environ['BACKEND_SERVICE_NAME']
        cls.health_check_name: str = os.environ['HEALTH_CHECK_NAME']
        cls.url_map_name: str = os.environ['URL_MAP_NAME']
        cls.url_map_path_matcher_name: str = os.environ[
            'URL_MAP_PATH_MATCHER_NAME']
        cls.target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
        cls.forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']

        # Shared services
        cls.k8s_api_manager = k8s.KubernetesApiManager(cls.k8s_context_name)
        cls.gcp_api_manager = gcp.GcpApiManager()
        cls.gcloud = gcp.GCloud(cls.gcp_api_manager, cls.project)
        cls.compute = cls.gcloud.compute

    @classmethod
    def tearDownClass(cls):
        cls.k8s_api_manager.close()
        cls.gcp_api_manager.close()

    def setUp(self):
        # todo(sergiitk): generate with run id
        # Traffic Director Configuration
        self.td = traffic_director.TrafficDirectorManager(
            self.gcloud, network=self.network)

        # Test Client Runner
        self.client_runner = xds_test_app.client.KubernetesClientRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.k8s_namespace),
            self.client_name,
            network=self.network,
            debug_use_port_forwarding=self.client_debug_use_port_forwarding)

        # Test Server Runner
        self.server_runner = xds_test_app.server.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.k8s_namespace),
            deployment_name=self.server_name,
            network=self.network,
            debug_reuse_service=self.server_debug_reuse_service)

    def tearDown(self):
        logger.debug(
            '############# tearDown(): resource cleanup initiated ############')
        self.td.delete_forwarding_rule(self.forwarding_rule_name)
        self.td.delete_target_grpc_proxy(self.target_proxy_name)
        self.td.delete_url_map(self.url_map_name)
        self.td.delete_backend_service(self.backend_service_name)
        self.td.delete_health_check(self.health_check_name)
        # self.td.cleanup()
        self.client_runner.cleanup()
        self.server_runner.cleanup()

    def test_ping_pong(self):
        # Traffic Director
        self.td.create_health_check(self.health_check_name)
        self.td.create_backend_service(self.backend_service_name)
        self.td.create_url_map(self.url_map_name,
                               self.url_map_path_matcher_name,
                               self.server_xds_host,
                               self.server_xds_port)
        self.td.create_target_grpc_proxy(self.target_proxy_name)
        self.td.create_forwarding_rule(self.forwarding_rule_name,
                                       self.server_xds_port)

        # Start test server
        test_server = self.server_runner.run(
            test_port=self.server_test_port,
            replica_count=self.server_replica_count)

        # Load Backends
        neg_name, neg_zones = self.server_runner.k8s_namespace.get_service_neg(
            self.server_runner.service_name, self.server_test_port)

        logger.info('Loading NEGs')
        backends = []
        for neg_zone in neg_zones:
            backend = self.gcloud.compute.wait_for_network_endpoint_group(
                neg_name, neg_zone)
            backends.append(backend)

        time.sleep(30)
        self.td.backend_service_add_backends(backends)

        logger.info('Fake waiting for Backend Service %s to become healthy',
                    self.td.backend_service.name)
        time.sleep(120)
        # gcp.wait_for_backends_healthy_status(self.compute, self.project,
        #                                      backend_service, backends)

        # Todo: get from TD
        test_server.xds_address = (self.server_xds_host, self.server_xds_port)

        # todo(sergiitk): make rpc enum or get it from proto
        # Start the client
        test_client = self.client_runner.run(
            server_address=test_server.xds_uri, rpc='UnaryCall', qps=30)

        # Run the test
        stats_response = test_client.request_load_balancer_stats(num_rpcs=10)

        # Check the results
        self.assertAllBackendsReceivedRpcs(stats_response)
        self.assertFailedRpcsAtMost(stats_response, 0)

    # todo(sergiitk): bring back as a sanity check when td cleanup is better
    # def test_zoo(self):
    #     self.assertEqual('FOO', 'FOO')

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


if __name__ == '__main__':
    absltest.main()
