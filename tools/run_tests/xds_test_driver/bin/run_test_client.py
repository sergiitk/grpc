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
from framework.infrastructure import k8s
from framework.test_app import client_app

logger = logging.getLogger(__name__)
# Flags
_CMD = flags.DEFINE_enum(
    'cmd', default='run', enum_values=['run', 'cleanup'],
    help='Command')
_QPS = flags.DEFINE_integer('qps', default=25, help='Queries per second')
_PRINT_RESPONSE = flags.DEFINE_bool(
    "print_response", default=False,
    help="Client prints responses")
flags.adopt_module_key_flags(xds_flags)
flags.adopt_module_key_flags(xds_k8s_flags)


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    command = _CMD.value

    k8s_api_manager = k8s.KubernetesApiManager(xds_k8s_flags.KUBE_CONTEXT.value)

    # Base namespace
    namespace = xds_flags.NAMESPACE.value
    client_namespace = namespace

    # Test client
    qps = _QPS.value
    print_response = _PRINT_RESPONSE.value
    client_port = xds_flags.CLIENT_PORT.value

    # Test server
    server_xds_host = xds_flags.SERVER_XDS_HOST.value
    server_xds_port = xds_flags.SERVER_XDS_PORT.value
    xds_uri = f'xds:///{server_xds_host}:{server_xds_port}'

    client_runner = client_app.KubernetesClientRunner(
        k8s.KubernetesNamespace(k8s_api_manager, client_namespace),
        deployment_name=xds_flags.CLIENT_NAME.value,
        image_name=xds_k8s_flags.CLIENT_IMAGE.value,
        gcp_service_account=xds_k8s_flags.GCP_SERVICE_ACCOUNT.value,
        network=xds_flags.NETWORK.value,
        td_bootstrap_image=xds_k8s_flags.TD_BOOTSTRAP_IMAGE.value,
        stats_port=client_port,
        reuse_namespace=True)

    if command == 'run':
        logger.info('Run client')
        client_runner.run(
            server_target=xds_uri, qps=qps, print_response=print_response)

    elif command == 'cleanup':
        logger.info('Cleanup client')
        client_runner.cleanup(force=True, force_namespace=False)


if __name__ == '__main__':
    app.run(main)
