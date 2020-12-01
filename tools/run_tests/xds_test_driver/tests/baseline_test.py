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
from absl.testing import absltest

from framework import xds_k8s_testcase

# Type aliases
XdsTestServer = xds_k8s_testcase.XdsTestServer
XdsTestClient = xds_k8s_testcase.XdsTestClient


class BaselineTest(xds_k8s_testcase.XdsKubernetesTestCase):
    def test_ping_pong(self):
        test_server: XdsTestServer = self.startTestServer()
        self.setupXdsForServer(test_server)
        test_client: XdsTestClient = self.startTestClientForServer(
            test_server, qps=30)

        # Run the test
        stats_response = test_client.request_load_balancer_stats(num_rpcs=10)

        # Check the results
        self.assertAllBackendsReceivedRpcs(stats_response)
        self.assertFailedRpcsAtMost(stats_response, 0)


if __name__ == '__main__':
    absltest.main()
