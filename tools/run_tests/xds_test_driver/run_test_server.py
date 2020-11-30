# Copyright 2016 gRPC authors.
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

from absl import app
from absl import flags

from framework import xds_flags
from framework import xds_k8s_flags
from infrastructure import k8s
import xds_test_app.server

logger = logging.getLogger(__name__)
# Flags
_MODE = flags.DEFINE_enum(
    'mode', default='run', enum_values=['run', 'cleanup'],
    help='Run mode.')
flags.adopt_module_key_flags(xds_flags)
flags.adopt_module_key_flags(xds_k8s_flags)


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    k8s_api_manager = k8s.KubernetesApiManager(
        xds_k8s_flags.KUBE_CONTEXT_NAME.value)
    server_runner = xds_test_app.server.KubernetesServerRunner(
        k8s.KubernetesNamespace(k8s_api_manager, xds_flags.NAMESPACE.value),
        deployment_name=xds_flags.SERVER_NAME.value,
        network=xds_flags.NETWORK.value,
        gcp_service_account=xds_k8s_flags.GCP_SERVICE_ACCOUNT.name,
        reuse_namespace=True)

    if _MODE.value == 'run':
        logger.info('Run server')
        server_runner.run(test_port=xds_flags.SERVER_PORT.value)
    elif _MODE.value == 'cleanup':
        logger.info('Cleanup server')
        server_runner.cleanup(force=True, force_namespace=True)


if __name__ == '__main__':
    app.run(main)
