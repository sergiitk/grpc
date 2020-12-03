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
import unittest

from absl.testing import absltest

from framework import xds_k8s_testcase
from tests import baseline_test

logger = logging.getLogger(__name__)
SKIP_REASON = 'Work in progress'

# Type aliases
XdsTestServer = xds_k8s_testcase.XdsTestServer
XdsTestClient = xds_k8s_testcase.XdsTestClient


class SecurityTest(xds_k8s_testcase.SecurityXdsKubernetesTestCase):
    def tearDown(self):
        # todo(sergiitk): remove
        logger.debug('######## tearDown(): resource cleanup initiated ########')
        super().tearDown()

    def test_mtls(self):
        self.setupSecureXds()

        test_server: XdsTestServer = self.startSecureTestServer()
        self.setupServerBackends()

        test_client: XdsTestClient = self.startSecureTestClientForServer(
            test_server, qps=30)

        # Run the test
        stats_response = test_client.request_load_balancer_stats(num_rpcs=200)

        # Check the results
        self.assertAllBackendsReceivedRpcs(stats_response)
        self.assertFailedRpcsAtMost(stats_response, 199)

    @absltest.skip(SKIP_REASON)
    def test_tls(self):
        pass

    @absltest.skip(SKIP_REASON)
    def test_plaintext_fallback(self):
        pass

    @absltest.skip(SKIP_REASON)
    def test_mtls_error(self):
        pass

    @absltest.skip(SKIP_REASON)
    def test_server_authz_error(self):
        pass


if __name__ == '__main__':
    absltest.main()
