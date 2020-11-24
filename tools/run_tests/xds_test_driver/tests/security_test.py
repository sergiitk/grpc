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
import os

import dotenv
import kubernetes.config
import kubernetes.client
from absl.testing import absltest
from googleapiclient import discovery as google_api
from absl import logging

from infrastructure import k8s
from infrastructure import gcp
import xds_test_app.client
import xds_test_app.server


class SecurityTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls):
        # todo(sergiitk): move to args
        dotenv.load_dotenv()
        # GCP
        cls.project: str = os.environ['PROJECT_ID']
        cls.network_name: str = os.environ['NETWORK_NAME']
        cls.network_url: str = f'global/networks/{cls.network_name}'
        #
        # Client
        cls.client_deployment_name = 'psm-grpc-client'

        cls.client_use_port_forwarding = bool(
            os.getenv('CLIENT_USE_PORT_FORWARDING', False))

        # K8s
        cls.k8s_context_name = os.environ['KUBE_CONTEXT_NAME']
        cls.k8s_namespace = os.environ['NAMESPACE']
        cls.server_name = os.environ['SERVER_NAME']
        cls.service_name = os.environ['SERVICE_NAME']
        cls.service_port = os.environ['SERVICE_PORT']
        cls.server_maintenance_port = os.environ['SERVER_MAINTENANCE_PORT']

        # Traffic director
        cls.backend_service_name = os.environ['GLOBAL_BACKEND_SERVICE_NAME']
        # health_check_name: str = os.environ['HEALTH_CHECK_NAME']
        # global_backend_service_name: str = os.environ[
        #     'GLOBAL_BACKEND_SERVICE_NAME']
        # url_map_name: str = os.environ['URL_MAP_NAME']
        # url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
        # target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
        # forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']
        cls.xds_service_host: str = 'sergii-psm-test-xds-host'
        cls.xds_service_port: int = 8000

        # Shared services
        cls.k8s_api_manager = k8s.KubernetesApiManager(cls.k8s_context_name)
        cls.compute = google_api.build('compute', 'v1', cache_discovery=False)

    @classmethod
    def tearDownClass(cls):
        cls.k8s_api_manager.close()

    def setUp(self):
        # todo(sergiitk): generate with run id
        # self.client_runner = xds_test_app.client.KubernetesClientRunner(
        #     k8s.KubernetesNamespace(self.k8s_api_manager, self.k8s_namespace),
        #     self.client_deployment_name,
        #     network_name=self.network_name,
        #     use_port_forwarding=self.client_use_port_forwarding)

        self.server_runner = xds_test_app.server.KubernetesServerRunner(
            k8s.KubernetesNamespace(self.k8s_api_manager, self.k8s_namespace),
            deployment_name=self.server_name,
            service_name=self.service_name,
            deployment_template='server-secure.deployment.yaml')

    def tearDown(self):
        # self.client_runner.cleanup()
        self.server_runner.cleanup()

    def test_mtls(self):
        test_server = self.server_runner.run(
            port=self.service_port,
            maintenance_port=self.server_maintenance_port,
            secure_mode=True)

        # # Load Backends
        # neg_name, neg_zones = self.server_runner.k8s_namespace.get_service_neg(
        #     self.server_runner.service_name, self.service_port)
        #
        # backends = []
        # for neg_zone in neg_zones:
        #     backend = gcp.get_network_endpoint_group(
        #         self.compute, self.project, neg_zone, neg_name)
        #     logging.info("Loaded backend: %s zone %s", backend.name,
        #                  backend.zone)
        #     backends.append(backend)
        #
        # # Global Backend Service (LB)
        # backend_service = gcp.get_backend_service(self.compute, self.project,
        #                                           self.backend_service_name)
        # logging.info('Loaded Global Backend Service %s', backend_service.name)
        # gcp.backend_service_add_backend(self.compute, self.project,
        #                                 backend_service, backends)
        # gcp.wait_for_backends_healthy_status(self.compute, self.project,
        #                                      backend_service, backends)
        # test_server.xds_address = (self.xds_service_host, self.xds_service_port)
        #
        # # todo(sergiitk): make rpc enum or get it from proto
        # test_client = self.client_runner.run(server_address=test_server.xds_uri,
        #                                      rpc='UnaryCall')
        # stats_response = test_client.request_load_balancer_stats(num_rpcs=9)
        # self.assertAllBackendsReceivedRpcs(stats_response)
        # self.assertFailedRpcsAtMost(stats_response, 0)

    def assertAllBackendsReceivedRpcs(self, stats_response):
        # todo(sergiitk): assert backends length
        logging.info(stats_response.rpcs_by_peer)
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
