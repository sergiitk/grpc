#!/usr/bin/env python3
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
from infrastructure import gcp
from infrastructure import traffic_director

logger = logging.getLogger(__name__)
# Flags
_CMD = flags.DEFINE_enum(
    'cmd', default='create', enum_values=['test', 'create', 'cleanup'],
    help='Command')
_SECURITY_MODE = flags.DEFINE_enum(
    'security_mode', default=None, enum_values=['mtls'],
    help='Configure td with security')
flags.adopt_module_key_flags(xds_flags)

BackendServiceProtocol = gcp.ComputeV1.BackendServiceProtocol


def create_all(td, server_xds_host, server_xds_port, security_mode=None):
    if security_mode is None:
        td.setup_for_grpc(server_xds_host, server_xds_port)
        return
    if security_mode == 'mtls':
        logger.info('Setting up mtls')
        td.setup_for_grpc(server_xds_host, server_xds_port,
                          backend_protocol=BackendServiceProtocol.HTTP2)
        td.backend_service_apply_client_mtls_policy(
            'projects/grpc-testing/locations/global/clientTlsPolicies/client_mtls_policy',
            'spiffe://grpc-testing.svc.id.goog/ns/sergii-psm-test/sa/psm-grpc-server')


def delete_all(td, security_mode):
    if security_mode == 'mtls':
        td.target_proxy_is_http=True
    td.cleanup(force=True)


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    gcp_api_manager = gcp.GcpApiManager()
    gcloud = gcp.GCloud(gcp_api_manager, xds_flags.PROJECT.value)
    td = traffic_director.TrafficDirectorManager(
        gcloud,
        namespace=xds_flags.NAMESPACE.value,
        network=xds_flags.NETWORK.value)
    server_xds_host = xds_flags.SERVER_XDS_HOST.value
    server_xds_port = xds_flags.SERVER_XDS_PORT.value
    security_mode = _SECURITY_MODE.value

    if _CMD.value == 'create':
        logger.info('Create-only mode')
        create_all(td, server_xds_host, server_xds_port, security_mode)
    elif _CMD.value == 'cleanup':
        logger.info('Cleanup mode')
        delete_all(td, security_mode)
    else:
        try:
            create_all(td, server_xds_host, server_xds_port)
            logger.info('Works!')
        finally:
            delete_all(td, security_mode)


if __name__ == '__main__':
    app.run(main)
