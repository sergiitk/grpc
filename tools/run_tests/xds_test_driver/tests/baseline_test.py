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

import xds_test_app.client
from infrastructure import k8s


class BaselineTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls):
        # todo(sergiitk): move to args
        dotenv.load_dotenv()
        # GCP
        # project: str = os.environ['PROJECT_ID']
        # network_name: str = os.environ['NETWORK_NAME']
        # network_url: str = f'global/networks/{network_name}'
        #
        # Client
        cls.client_host_override = os.environ['CLIENT_HOST_OVERRIDE']
        cls.client_stats_port: int = 8079

        # K8s
        kube_context_name = os.environ['KUBE_CONTEXT_NAME']
        cls.namespace = os.environ['NAMESPACE']
        # service_name = os.environ['SERVICE_NAME']
        # service_port = os.environ['SERVICE_PORT']
        # health_check_name: str = os.environ['HEALTH_CHECK_NAME']
        # global_backend_service_name: str = os.environ[
        #     'GLOBAL_BACKEND_SERVICE_NAME']
        # url_map_name: str = os.environ['URL_MAP_NAME']
        # url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
        # target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
        # forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']
        # xds_service_hostname: str = 'sergii-psm-test-xds-host'
        # xds_service_port: int = 8000
        # xds_service_host: str = f'{xds_service_hostname}:{xds_service_port}'
        # Connect k8s
        kubernetes.config.load_kube_config(context=kube_context_name)
        cls.k8s_client = kubernetes.client.ApiClient()

    def _xds_client(self, stats_port=None, host_override=None):
        if stats_port is None:
            stats_port = self.client_stats_port
        if host_override is None:
            host_override = self.client_host_override
        return k8s.xds_test_client(self.k8s_client, self.namespace,
                                   stats_port=stats_port,
                                   host_override=host_override)

    def test_ping_pong(self):
        with self._xds_client() as xds_client:
            result = xds_client.request_load_balancer_stats(num_rpcs=2)
            self.assertEqual(result, 'FOO')


if __name__ == '__main__':
    absltest.main()
