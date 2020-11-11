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

from googleapiclient import discovery as google_api
from kubernetes import client as kube_client
from kubernetes import config as kube_config
import dotenv

from infrastructure import traffic_director, gcp


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
    group_gcp.add_argument('--project_id', help='GCP project id', required=True)
    group_gcp.add_argument(
        '--network', default='global/networks/default-vpc',
        help='GCP network to use')
    group_gcp.add_argument('--zone', default='us-central1-a')

    group_xds = parser.add_argument_group('xDS settings')
    group_xds.add_argument(
        '--xds_server', default='trafficdirector.googleapis.com:443',
        help='xDS server')

    group_driver = parser.add_argument_group('Driver settings')
    group_driver.add_argument(
        '--stats_port', default=8079, type=int,
        help='Local port for the client process to expose the LB stats service')
    group_driver.add_argument(
        '--verbose', action='store_true',
        help='verbose log output')
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # local args shortcuts
    project: str = args.project_id
    network: str = args.network

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

    # Connect k8s
    kube_config.load_kube_config(context=kube_context_name)
    k8s_core_v1: kube_client.CoreV1Api = kube_client.CoreV1Api()

    # Create compute client
    # todo(sergiitk): see if cache_discovery=False needed
    compute: google_api.Resource = google_api.build(
        'compute', 'v1', cache_discovery=False)

    td: traffic_director.TrafficDirectorState = traffic_director.setup_gke(
        k8s_core_v1, compute,
        project, namespace, network,
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


if __name__ == '__main__':
    main()
