# Copyright 2020 gRPC authors.
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
import logging

from absl import flags
from absl.testing import absltest
import absl.testing.xml_reporter

from framework import xds_k8s_testcase
from framework.test_cases import base_testcase

logger = logging.getLogger(__name__)
flags.adopt_module_key_flags(xds_k8s_testcase)

# Type aliases
_XdsTestServer = xds_k8s_testcase.XdsTestServer
_XdsTestClient = xds_k8s_testcase.XdsTestClient


class BaselineTest(xds_k8s_testcase.RegularXdsKubernetesTestCase):
    # def test_traffic_director_grpc_setup(self):
    #     with self.subTest("0_create_health_check"):
    #         self.assertEqual(True, True)
    #
    #     with self.subTest("1_create_backend_service"):
    #         self.assertEqual(True, True)
    #
    #     with self.subTest("2_create_url_map"):
    #         self.assertEqual("2_create_url_map", None)
    #
    #     with self.subTest("3_create_target_proxy"):
    #         self.assertEqual(True, True)
    #
    #     with self.subTest("4_create_forwarding_rule"):
    #         self.assertEqual("4_create_forwarding_rule", None)
    #
    def test_3_good(self):
        self.assertEqual(True, True)

    def test_2_unexpected(self):
        raise ValueError("Unexpected")

    #
    # def test_1_failure(self):
    #     logger.info(
    #         "test_1_another,test_1_another,test_1_another,test_1_another"
    #     )
    #     self.assertEqual("test_1_failure", None)

    # @absltest.skip("demonstrating skipping")
    # def test_nothing(self):
    #     self.fail("shouldn't happen")

    # def test_2_traffic_director_grpc_setup(self):
    #     self.assertEqual("test grpc setup", None)


if __name__ == "__main__":
    absltest.main(failfast=False)
