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
from framework.infrastructure import gcp
from framework.infrastructure import traffic_director

logger = logging.getLogger(__name__)
# Flags
_CMD = flags.DEFINE_enum(
    'cmd', default='create', enum_values=['cycle', 'create', 'cleanup'],
    help='Command')
_SECURITY_MODE = flags.DEFINE_enum(
    'security_mode', default=None, enum_values=['mtls'],
    help='Configure td with security')
flags.adopt_module_key_flags(xds_flags)
flags.adopt_module_key_flags(xds_k8s_flags)

BackendServiceProtocol = gcp.ComputeV1.BackendServiceProtocol


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    gcp_api_manager = gcp.GcpApiManager()
    command = _CMD.value
    security_mode = _SECURITY_MODE.value
    server_xds_host = xds_flags.SERVER_XDS_HOST.value
    server_xds_port = xds_flags.SERVER_XDS_PORT.value

    if security_mode is None:
        td = traffic_director.TrafficDirectorManager(
            gcp_api_manager,
            project=xds_flags.PROJECT.value,
            resource_prefix=xds_flags.NAMESPACE.value,
            network=xds_flags.NETWORK.value)
    else:
        td = traffic_director.TrafficDirectorSecureManager(
            gcp_api_manager,
            project=xds_flags.PROJECT.value,
            resource_prefix=xds_flags.NAMESPACE.value,
            network=xds_flags.NETWORK.value)

    # noinspection PyBroadException
    try:
        if command == 'create' or command == 'cycle':
            logger.info('Create-only mode')
            if security_mode is None:
                logger.info('No security')
                td.setup_for_grpc(server_xds_host, server_xds_port)

            elif security_mode == 'mtls':
                logger.info('Setting up mtls')
                td.setup_for_grpc(server_xds_host, server_xds_port)
                td.setup_client_security('sergii-psm-test', 'sergii-psm-test')
                td.setup_server_security(8080)

            logger.info('Works!')
    except Exception:
        logger.exception('Got error during creation')

    if command == 'cleanup' or command == 'cycle':
        logger.info('Cleaning up')
        td.cleanup(force=True)


if __name__ == '__main__':
    app.run(main)
