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

from infrastructure import k8s
import xds_test_app.client

logger = logging.getLogger(__name__)
# Flags
_PROJECT = flags.DEFINE_string(
    "project", default=None, help="GCP Project ID, required")
_NAMESPACE = flags.DEFINE_string(
    "namespace", default=None,
    help="Isolate GCP resources using given namespace / name prefix")
_KUBE_CONTEXT_NAME = flags.DEFINE_string(
    "kube_context_name", default=None, help="Kubectl context to use")
_GCP_SERVICE_ACCOUNT = flags.DEFINE_string(
    "gcp_service_account", default=None,
    help="GCP Service account for GKE workloads to impersonate")
_NETWORK = flags.DEFINE_string(
    "network", default="default", help="GCP Network ID")
_CLIENT_NAME = flags.DEFINE_string(
    "client_name", default="psm-grpc-client",
    help="Client deployment and service name")
_SERVER_NAME = flags.DEFINE_string(
    "server_name", default="psm-grpc-server",
    help="Server deployment and service name")
_SERVER_PORT = flags.DEFINE_integer(
    "server_port", default=8080,
    help="Server test port")
_CLIENT_PORT_FORWARDING = flags.DEFINE_bool(
    "client_debug_use_port_forwarding", default=False,
    help="Development only: use kubectl port-forward to connect to test client")
_MODE = flags.DEFINE_enum(
    'mode', default='run', enum_values=['run', 'cleanup'],
    help='Run mode.')
flags.mark_flags_as_required([
    "project",
    "namespace",
    "gcp_service_account",
    "kube_context_name"
])


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    k8s_api_manager = k8s.KubernetesApiManager(_KUBE_CONTEXT_NAME.value)
    client_runner = xds_test_app.client.KubernetesClientRunner(
        k8s.KubernetesNamespace(k8s_api_manager, _NAMESPACE.value),
        deployment_name=_CLIENT_NAME.value,
        network=_NETWORK.value,
        gcp_service_account=_GCP_SERVICE_ACCOUNT.name,
        reuse_namespace=True)

    if _MODE.value == 'run':
        logger.info('Run client')
        client_runner.run(
            server_address=f'{_SERVER_NAME.value}:{_SERVER_PORT.value}')
    elif _MODE.value == 'cleanup':
        logger.info('Cleanup client')
        client_runner.cleanup(force=True)


if __name__ == '__main__':
    app.run(main)
