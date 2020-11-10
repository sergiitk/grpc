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

from googleapiclient import errors as google_api_errors

from infrastructure import gcp
from infrastructure import k8s

logger = logging.getLogger()


def setup_gke(
    k8s_core_v1, compute,
    project, namespace, network,
    service_name, service_port,
    global_backend_service_name, health_check_name,
    url_map_name, url_map_path_matcher_name,
    target_proxy_name, forwarding_rule_name,
    xds_service_host, xds_service_port
):
    # Detect NEG name
    neg_name, neg_zones = k8s.get_service_neg(k8s_core_v1, namespace,
                                              service_name, service_port)
    logger.info("Detected NEG=%s in zones=%s", neg_name, neg_zones)

    # Load NEGs
    negs = [gcp.get_network_endpoint_group(compute, project, neg_zone, neg_name)
            for neg_zone in neg_zones]

    # Health check
    try:
        health_check = gcp.get_health_check(compute, project, health_check_name)
        logger.info('Loaded TCP HealthCheck %s', health_check.name)
    except google_api_errors.HttpError:
        logger.info('Creating TCP HealthCheck %s', health_check_name)
        health_check = gcp.create_tcp_health_check(compute, project,
                                                   health_check_name)

    # Global Backend Service (LB)
    try:
        global_backend_service = gcp.get_global_backend_service(
            compute, project, global_backend_service_name)
        logger.info('Loaded Backend Service %s', global_backend_service.name)
    except google_api_errors.HttpError:
        logger.info('Creating Backend Service %s', global_backend_service_name)
        global_backend_service = gcp.create_global_backend_service(
            compute, project, global_backend_service_name, health_check)
        # Add NEGs as backends of Global Backend Service
        logger.info(
            'Add NEG %s in zones %s as backends to the Backend Service %s',
            neg_name, neg_zones, global_backend_service.name)
        gcp.backend_service_add_backend(compute, project,
                                        global_backend_service, negs)

    # URL map
    try:
        url_map = gcp.get_url_map(compute, project, url_map_name)
        logger.info('Loaded URL Map %s', url_map.name)
    except google_api_errors.HttpError:
        logger.info('Creating URL map %s xds://%s -> %s',
                    url_map_name,
                    xds_service_host,
                    global_backend_service.name)
        url_map = gcp.create_url_map(compute, project,
                                     url_map_name, url_map_path_matcher_name,
                                     xds_service_host, global_backend_service)

    # Target Proxy
    try:
        target_proxy = gcp.get_target_proxy(compute, project,
                                            target_proxy_name)
        logger.info('Loaded target proxy %s', target_proxy.name)
    except google_api_errors.HttpError:
        logger.info('Creating target proxy %s to url map %s',
                    target_proxy_name, url_map.url)
        target_proxy = gcp.create_target_proxy(
            compute, project,
            target_proxy_name, url_map)

    # Global Forwarding Rule
    try:
        forwarding_rule = gcp.get_forwarding_rule(compute, project,
                                                  forwarding_rule_name)
        logger.info('Loaded forwarding rule %s', forwarding_rule.name)
    except google_api_errors.HttpError:
        logger.info('Creating forwarding rule %s 0.0.0.0:%s -> %s in %s',
                    forwarding_rule_name, xds_service_port,
                    target_proxy.url, network)
        forwarding_rule = gcp.create_forwarding_rule(
            compute, project,
            forwarding_rule_name, xds_service_port,
            target_proxy, network)
