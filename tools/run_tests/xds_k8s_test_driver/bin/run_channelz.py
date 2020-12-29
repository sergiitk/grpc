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
import hashlib
import logging

from absl import app
from absl import flags

from framework import xds_flags
from framework import xds_k8s_flags
from framework.infrastructure import k8s
from framework.rpc import grpc_channelz
from framework.test_app import server_app
from framework.test_app import client_app

logger = logging.getLogger(__name__)
# Flags
_SERVER_RPC_HOST = flags.DEFINE_string('server_rpc_host',
                                       default='127.0.0.1',
                                       help='Server RPC host')
_CLIENT_RPC_HOST = flags.DEFINE_string('client_rpc_host',
                                       default='127.0.0.1',
                                       help='Client RPC host')
_SECURITY = flags.DEFINE_enum('security',
                              default='positive_cases',
                              enum_values=['positive_cases', 'mtls_error'],
                              help='Test for security setup')
flags.adopt_module_key_flags(xds_flags)
flags.adopt_module_key_flags(xds_k8s_flags)

# Type aliases
_Channel = grpc_channelz.Channel
_Socket = grpc_channelz.Socket
_XdsTestServer = server_app.XdsTestServer
_XdsTestClient = client_app.XdsTestClient
_ClientChannelState = client_app.ChannelState


def debug_cert(cert):
    if not cert:
        return '<missing>'
    sha1 = hashlib.sha1(cert)
    return f'sha1={sha1.hexdigest()}, len={len(cert)}'


def debug_sock_tls(tls):
    return (f'local:  {debug_cert(tls.local_certificate)}\n'
            f'remote: {debug_cert(tls.remote_certificate)}')


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
    test_server: _XdsTestServer = _XdsTestServer(
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

    test_client: _XdsTestClient = _XdsTestClient(
        ip=client_pod_ip,
        server_target=test_server.xds_uri,
        rpc_port=client_port,
        rpc_host=_CLIENT_RPC_HOST.value)

    if _SECURITY.value in 'positive_cases':
        # Positive cases: mTLS, TLS, Plaintext
        test_client.wait_for_active_server_channel()
        client_sock: _Socket = test_client.get_active_server_channel_socket()
        server_sock: _Socket = test_server.get_server_socket_matching_client(
            client_sock)

        server_tls = server_sock.security.tls
        client_tls = client_sock.security.tls

        print(f'\nServer certs:\n{debug_sock_tls(server_tls)}')
        print(f'\nClient certs:\n{debug_sock_tls(client_tls)}')
        print()

        if server_tls.local_certificate:
            eq = server_tls.local_certificate == client_tls.remote_certificate
            print(f'(TLS)  Server local matches client remote: {eq}')
        else:
            print('(TLS)  Not detected')

        if server_tls.remote_certificate:
            eq = server_tls.remote_certificate == client_tls.local_certificate
            print(f'(mTLS) Server remote matches client local: {eq}')
        else:
            print('(mTLS) Not detected')

    elif _SECURITY.value == 'mtls_error':
        # Negative case
        # Channel side
        client_correct_setup = True
        channel: _Channel = test_client.wait_for_server_channel_state(
            state=_ClientChannelState.TRANSIENT_FAILURE)
        try:
            subchannel, *subchannels = list(
                test_client.channelz.list_channel_subchannels(channel))
        except ValueError:
            print("(mTLS-error) Client setup fail: subchannel not found. "
                  "Common causes: test client didn't connect to TD; "
                  "test client exhausted retries, and closed all subchannels.")
            return

        logger.debug('Found subchannel, %r', subchannel)
        if subchannels:
            client_correct_setup = False
            print(f'(mTLS-error) Unexpected subchannels {subchannels}')

        subchannel_state: _ClientChannelState = subchannel.data.state.state
        if subchannel_state is not _ClientChannelState.TRANSIENT_FAILURE:
            client_correct_setup = False
            print('(mTLS-error) Subchannel expected to be in '
                  'TRANSIENT_FAILURE, same as its channel')

        sockets = list(
            test_client.channelz.list_subchannels_sockets(subchannel))
        if sockets:
            client_correct_setup = False
            print(f'(mTLS-error) Unexpected subchannel sockets {sockets}')

        if client_correct_setup:
            print(f'(mTLS-error) Client setup pass: the channel '
                  f'to the server has exactly one subchannel '
                  f'in TRANSIENT_FAILURE, and no sockets')

        # Server side
        server_sockets = list(test_server.get_test_server_sockets())
        if server_sockets:
            print('(mTLS-error) Server setup fail:'
                  f' unexpected sockets {sockets}')
        else:
            print(f'(mTLS-error) Server setup pass: test server has no sockets')

    test_client.close()
    test_server.close()


if __name__ == '__main__':
    app.run(main)
