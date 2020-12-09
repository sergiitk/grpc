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
from framework.test_app import server_app
from framework.test_app import client_app

logger = logging.getLogger(__name__)
# Flags
_SERVER_RPC_HOST = flags.DEFINE_string(
    'server_rpc_host', default='127.0.0.1', help='Server RPC host')
_CLIENT_RPC_HOST = flags.DEFINE_string(
    'client_rpc_host', default='127.0.0.1', help='Client RPC host')
flags.adopt_module_key_flags(xds_flags)
flags.adopt_module_key_flags(xds_k8s_flags)

# Type aliases
XdsTestServer = server_app.XdsTestServer
XdsTestClient = client_app.XdsTestClient


def get_deployment_pod_ips(k8s_ns, deployment_name):
    deployment = k8s_ns.get_deployment(deployment_name)
    pods = k8s_ns.list_deployment_pods(deployment)
    return [pod.status.pod_ip for pod in pods]


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    k8s_api_manager = k8s.KubernetesApiManager(xds_k8s_flags.KUBE_CONTEXT.value)

    # Namespaces
    namespace = xds_flags.NAMESPACE.value
    server_namespace = namespace
    client_namespace = namespace

    # Server
    server_k8s_ns = k8s.KubernetesNamespace(k8s_api_manager, server_namespace)
    server_name = xds_flags.SERVER_NAME.value
    server_port = xds_flags.SERVER_PORT.value
    server_pod_ip = get_deployment_pod_ips(server_k8s_ns, server_name)[0]
    test_server: XdsTestServer = XdsTestServer(
        ip=server_pod_ip,
        rpc_port=server_port,
        xds_host=xds_flags.SERVER_XDS_HOST.value,
        xds_port=xds_flags.SERVER_XDS_PORT.value,
        rpc_host=_SERVER_RPC_HOST.value)

    # Client
    client_k8s_ns = k8s.KubernetesNamespace(k8s_api_manager, client_namespace)
    client_name = xds_flags.CLIENT_NAME.value
    client_port = xds_flags.CLIENT_PORT.value
    client_pod_ip = get_deployment_pod_ips(client_k8s_ns, client_name)[0]

    test_client: XdsTestClient = XdsTestClient(
        ip=client_pod_ip,
        server_target=test_server.xds_uri,
        rpc_port=client_port,
        rpc_host=_CLIENT_RPC_HOST.value)

    with test_client:
        test_client.wait_for_healthy_server_channel()
        channel = test_client.get_healthy_server_channel()
        print(channel)
        stats_response = test_client.get_load_balancer_stats(num_rpcs=10)
        print(stats_response)


if __name__ == '__main__':
    app.run(main)
