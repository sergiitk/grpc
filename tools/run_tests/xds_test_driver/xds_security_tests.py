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
import json
import logging
import time
from typing import List, Tuple

from kubernetes import client as kube_client, config as kube_config
from kubernetes.client import CoreV1Api, CoreApi
from kubernetes.client.models import V1Service

_WAIT_FOR_OPERATION_SEC = 1200
_GCP_API_RETRIES = 5


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


def wait_for_global_operation(gcp,
                              operation,
                              timeout_sec=_WAIT_FOR_OPERATION_SEC):
    start_time = time.time()
    while time.time() - start_time <= timeout_sec:
        result = gcp.compute.globalOperations().get(
            project=gcp.project,
            operation=operation).execute(num_retries=_GCP_API_RETRIES)
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(2)
    raise Exception('Operation %s did not complete within %d' %
                    (operation, timeout_sec))


# def create_tcp_health_check(gcp, name):
#     tcp_health_check_spec = {
#         'name': name,
#         'type': 'TCP',
#         'tcpHealthCheck': {
#             'portSpecification': 'USE_SERVING_PORT',
#         }
#     }
#     logger.debug('Sending GCP request with body=%s', config)
#     result = gcp.compute.healthChecks().insert(
#         project=gcp.project, body=tcp_health_check_spec).execute(num_retries=_GCP_API_RETRIES)
#     wait_for_global_operation(gcp, result['name'])
#     gcp.health_check = GcpResource(result['name'], result['targetLink'])


# def get_health_check(gcp, health_check_name):
#     result = gcp.compute.healthChecks().get(
#         project=gcp.project, healthCheck=health_check_name).execute()
#     gcp.health_check = GcpResource(health_check_name, result['selfLink'])
#     # V1Service.status;
#     # x: property = V1Service.metadata;
#     z = V1Service.metadata
#     print(z)
    # z.
    # z.

def k8s_get_service_neg(k8s_core_v1: CoreV1Api, service_name: str, namespace: str,
    service_port: int) -> Tuple[str, List[str]]:
    logger.debug('Detecting NEG name for service=%s', service_name)
    service: V1Service = k8s_core_v1.read_namespaced_service(service_name,
                                                             namespace,
                                                             async_req=False)

    neg_info: dict = json.loads(
        service.metadata.annotations['cloud.google.com/neg-status'])
    neg_name: str = neg_info['network_endpoint_groups'][str(service_port)]
    neg_zones: List[str] = neg_info['zones']
    return neg_name, neg_zones

class GcpResource:
    def __init__(self, name, url):
        self.name = name
        self.url = url


class GcpState:
    def __init__(self, compute, project):
        self.compute = compute
        # self.alpha_compute = alpha_compute
        self.project = project
        self.health_check = None
        self.health_check_firewall_rule = None
        self.backend_services = []
        self.url_map = None
        self.target_proxy = None
        self.global_forwarding_rule = None
        self.service_port = None


def k8s_print_server_mappings(k8s_root):
    logger.debug("Server mappings:")
    for mapping in k8s_root.get_api_versions().server_address_by_client_cid_rs:
        logger.debug('%s -> %s', mapping.client_cidr, mapping.server_address)


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # local args shortcuts
    project: str = args.project_id
    zone: str = args.zone

    # todo(sergiitk): move to args
    kube_context_name = 'gke_grpc-testing_us-central1-a_gke-interop-xds-test1-us-central1'
    namespace = 'default'
    service_name = 'psm-grpc-service'
    service_port = 8080
    health_check_name = "sergii-psm-test-health-check"

    # Connect k8s
    kube_config.load_kube_config(context=kube_context_name)
    k8s_root: CoreApi = kube_client.CoreApi()
    k8s_core_v1: CoreV1Api = kube_client.CoreV1Api()

    if args.verbose:
        k8s_print_server_mappings(k8s_root)

    # Detect NEG name
    neg_name, neg_zones = k8s_get_service_neg(k8s_core_v1, service_name, namespace,
                                              service_port)
    logger.info("Detected NEG=%s in zones=%s", neg_name, neg_zones)


    # compute = googleapiclient.discovery.build('compute', 'v1',
    #                                           cache_discovery=False)
    # gcp = GcpState(compute, project)
    #
    # if args.use_existing_gcp_resources:
    #     create_tcp_health_check(gcp, health_check_name)
    #     print(f"Created healthcheck = {gcp.health_check.name} @ {gcp.health_check.url}")
    # else:
    #     get_health_check(gcp, health_check_name)

    # confirm NEG
    # result = compute.networkEndpointGroups().get(project=project, zone=zone, networkEndpointGroup=neg_name).execute()


if __name__ == '__main__':
    main()
