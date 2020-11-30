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

from infrastructure import gcp
from infrastructure import traffic_director

logger = logging.getLogger(__name__)
# Flags
_PROJECT = flags.DEFINE_string(
    "project", default=None, help="GCP Project ID, required")
_NAMESPACE = flags.DEFINE_string(
    "namespace", default=None,
    help="Isolate GCP resources using given namespace / name prefix")
_SERVER_XDS_HOST = flags.DEFINE_string(
    "server_xds_host", default='xds-test-server',
    help="Test server xDS hostname")
_SERVER_XDS_PORT = flags.DEFINE_integer(
    "server_xds_port", default=8000, help="Test server xDS port")
_NETWORK = flags.DEFINE_string(
    "network", default="default", help="GCP Network ID")
_MODE = flags.DEFINE_enum(
    'mode', default='full', enum_values=['full', 'create', 'cleanup'],
    help='Job status.')
flags.mark_flags_as_required(["project", "namespace"])


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')

    gcp_api_manager = gcp.GcpApiManager()
    gcloud = gcp.GCloud(gcp_api_manager, _PROJECT.value)
    td = traffic_director.TrafficDirectorManager(
        gcloud, namespace=_NAMESPACE.value, network=_NETWORK.value)

    def create_all():
        td.setup_for_grpc(
            f'{_NAMESPACE.value}-{_SERVER_XDS_HOST.value}',
            _SERVER_XDS_PORT.value)

    def delete_all():
        td.cleanup(force=True)

    if _MODE.value == 'create':
        logger.info('Create-only mode')
        create_all()
    elif _MODE.value == 'cleanup':
        logger.info('Cleanup mode')
        delete_all()
    else:
        try:
            create_all()
            logger.info('Works!')
        finally:
            delete_all()


if __name__ == '__main__':
    app.run(main)
