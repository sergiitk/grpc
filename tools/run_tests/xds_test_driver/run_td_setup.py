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

import argparse
import logging
import os
from typing import Optional

from googleapiclient import discovery as google_api
import kubernetes.client
import kubernetes.config
import dotenv

import xds_test_app.client
from infrastructure import traffic_director
from infrastructure import gcp
from infrastructure import k8s


logger = logging.getLogger()
console_handler = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s: %(levelname)-8s %(message)s')
console_handler.setFormatter(formatter)
logger.handlers = []
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Run xDS security interop tests on GCP')

    group_gcp = parser.add_argument_group('GCP settings')
    group_gcp.add_argument('--project_id', help='Project ID', required=True)
    group_gcp.add_argument(
        '--network', default='default-vpc',
        help='Network ID')

    group_driver = parser.add_argument_group('Test client settings')
    group_driver.add_argument(
        '--client_host_override', type=str,
        help='Do not detect test client host automatically. Use this options '
             'for debugging locally (with port forwarding)')
    group_driver.add_argument(
        '--client_stats_port', default=8079, type=int,
        help='The port of LoadBalancerStatsService on the client')

    group_driver = parser.add_argument_group('Driver settings')
    group_driver.add_argument(
        '--verbose', action='store_true',
        help='Verbose log output')
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # GCP
    project: str = args.project_id
    network_url: str = f'global/networks/{args.network}'

    # Client
    client_host_override: Optional[str] = args.client_host_override
    client_stats_port: int = args.client_stats_port

    # todo(sergiitk): move to args
    dotenv.load_dotenv()
    kube_context_name = os.environ['KUBE_CONTEXT_NAME']
    namespace = os.environ['NAMESPACE']
    service_name = os.environ['SERVICE_NAME']
    service_port = os.environ['SERVICE_PORT']
    health_check_name: str = os.environ['HEALTH_CHECK_NAME']
    global_backend_service_name: str = os.environ['GLOBAL_BACKEND_SERVICE_NAME']
    url_map_name: str = os.environ['URL_MAP_NAME']
    url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
    target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
    forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']
    xds_service_hostname: str = 'sergii-psm-test-xds-host'
    xds_service_port: str = '8000'
    xds_service_host: str = f'{xds_service_hostname}:{xds_service_port}'
    # todo(sergiitk): detect automatically

    # Connect k8s
    kubernetes.config.load_kube_config(context=kube_context_name)
    k8s_client = kubernetes.client.ApiClient()
    k8s_core_v1 = kubernetes.client.CoreV1Api(k8s_client)

    # Create compute client
    # todo(sergiitk): see if cache_discovery=False needed
    compute: google_api.Resource = google_api.build(
        'compute', 'v1', cache_discovery=False)

    td: traffic_director.TrafficDirectorState = traffic_director.setup_gke(
        k8s_core_v1, compute,
        project, namespace, network_url,
        service_name, service_port,
        global_backend_service_name, health_check_name,
        url_map_name, url_map_path_matcher_name,
        target_proxy_name, forwarding_rule_name,
        xds_service_host, xds_service_port)

    # Wait for global backend instance reporting all backends to be HEALTHY.
    gcp.wait_for_backends_healthy_status(compute, project,
                                         td.backend_service, td.backends)

    # todo(sergiitk): finally/context manager.
    compute.close()
    k8s_client.close()


if __name__ == '__main__':
    main()
