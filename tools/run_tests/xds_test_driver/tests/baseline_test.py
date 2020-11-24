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
from absl import logging

from infrastructure import k8s
import xds_test_app.client


class BaselineTest(absltest.TestCase):
    k8s_client = None

    @classmethod
    def setUpClass(cls):
        # todo(sergiitk): move to args
        dotenv.load_dotenv()
        # GCP
        # project: str = os.environ['PROJECT_ID']
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
        # service_name = os.environ['SERVICE_NAME']
        # service_port = os.environ['SERVICE_PORT']

        # Traffic director
        # health_check_name: str = os.environ['HEALTH_CHECK_NAME']
        # global_backend_service_name: str = os.environ[
        #     'GLOBAL_BACKEND_SERVICE_NAME']
        # url_map_name: str = os.environ['URL_MAP_NAME']
        # url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
        # target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
        # forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']
        cls.xds_service_hostname: str = 'sergii-psm-test-xds-host'
        cls.xds_service_port: int = 8000
        cls.xds_service_host: str = (f'{cls.xds_service_hostname}:'
                                     f'{cls.xds_service_port}')
        cls.xds_service_address = f'xds:///{cls.xds_service_host}'

        # Shared services
        cls.k8s_api_manager = k8s.KubernetesApiManager(cls.k8s_context_name)

    @classmethod
    def tearDownClass(cls):
        cls.k8s_api_manager.close()

    def setUp(self):
        # todo(sergiitk): generate with run id
        k8s_namespace_client = k8s.KubernetesNamespace(
            self.k8s_api_manager, self.k8s_namespace)

        self.client_runner = xds_test_app.client.KubernetesClientRunner(
            k8s_namespace_client,
            self.client_deployment_name,
            network_name=self.network_name,
            use_port_forwarding=self.client_use_port_forwarding)

    def tearDown(self):
        self.k8s_manager = None
        self.client_runner.cleanup()
        self.client_runner = None

    def test_ping_pong(self):
        # todo(sergiitk): make rpc enum or get it from proto
        xds_test_client = self.client_runner.run(
            server_address=self.xds_service_address,
            rpc='UnaryCall')
        stats_response = xds_test_client.request_load_balancer_stats(num_rpcs=9)
        self.assertAllBackendsReceivedRpcs(stats_response)
        self.assertFailedRpcsAtMost(stats_response, 0)

    def test_zoo(self):
        self.assertEqual('FOO', 'FOO')

    def assertAllBackendsReceivedRpcs(self, stats_response):
        # todo(sergiitk): assert backends length
        logging.info(stats_response.rpcs_by_peer)
        for backend, rpcs_count in stats_response.rpcs_by_peer.items():
            with self.subTest(f'Backend {backend} received RPCs'):
                self.assertGreater(int(rpcs_count), 0,
                                   msg='Did not receive a single RPC')

    def assertFailedRpcsAtMost(self, stats_response, count):
        self.assertLessEqual(int(stats_response.num_failures), count,
                             msg='Unexpected number of RPC failures'
                                 f'{stats_response.num_failures} > {count}')


if __name__ == '__main__':
    absltest.main()
