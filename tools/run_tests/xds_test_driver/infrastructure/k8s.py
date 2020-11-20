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

import json
import logging
import pathlib
import contextlib
from typing import Tuple, List

import retrying
import yaml
from kubernetes import client
from kubernetes import utils

import xds_test_app.client

logger = logging.getLogger()


def simple_resource_get(func):
    def wrap_not_found_return_none(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except client.ApiException as e:
            if e.status == 404:
                # noinspection PyBroadException
                try:
                    # Try parsing nicer error from the body
                    data = json.loads(e.body)
                    logger.debug(data['message'])
                except Exception:
                    logger.debug('Resource not found. %s', e.body)
                return None
            raise

    return wrap_not_found_return_none


def get_service_neg(
    k8s_core_v1: client.CoreV1Api, namespace: str,
    service_name: str, service_port: int,
) -> Tuple[str, List[str]]:
    logger.info('Detecting NEG name for service=%s in namespace=%s',
                service_name, namespace)
    service: client.V1Service = k8s_core_v1.read_namespaced_service(
        service_name, namespace)

    neg_info: dict = json.loads(
        service.metadata.annotations['cloud.google.com/neg-status'])
    neg_name: str = neg_info['network_endpoint_groups'][str(service_port)]
    neg_zones: List[str] = neg_info['zones']
    return neg_name, neg_zones


def debug_server_mappings(k8s_root: client.CoreApi):
    logger.debug("Server mappings:")
    for mapping in k8s_root.get_api_versions().server_address_by_client_cid_rs:
        logger.debug('%s -> %s', mapping.client_cidr, mapping.server_address)


def label_dict_to_selector(labels: dict) -> str:
    return ','.join(f'{k}=={v}' for k, v in labels.items())


def list_pods_with_labels(k8s_client,
                          namespace,
                          labels: dict) -> List[client.V1Pod]:
    api_core = client.CoreV1Api(k8s_client)
    pod_list: client.V1PodList = api_core.list_namespaced_pod(
        namespace, label_selector=label_dict_to_selector(labels))
    return pod_list.items


def get_deployment_pods(k8s_client,
                        namespace,
                        deployment: client.V1Deployment) -> List[client.V1Pod]:
    # V1LabelSelector.match_expressions not supported at the moment
    return list_pods_with_labels(
        k8s_client, namespace, deployment.spec.selector.match_labels)


def _pod_started(pod: client.V1Pod):
    return pod.status.phase not in ('Pending', 'Unknown')


def get_pod(k8s_client, namespace, name) -> client.V1Pod:
    api_core = client.CoreV1Api(k8s_client)
    return api_core.read_namespaced_pod(name, namespace)


def wait_for_started_pod(k8s_client, namespace,
                         pod: client.V1Pod,
                         timeout_sec=60,
                         wait_sec=1) -> client.V1Pod:
    if _pod_started(pod):
        return pod

    @retrying.retry(retry_on_result=lambda r: not _pod_started(r),
                    stop_max_delay=timeout_sec * 1000,
                    wait_fixed=wait_sec * 1000)
    def _get_started_pod_with_retry():
        updated_pod = get_pod(k8s_client, namespace, pod.metadata.name)
        logger.info('Waiting for pod %s to start, current phase: %s',
                    updated_pod.metadata.name,
                    updated_pod.status.phase)
        return updated_pod

    return _get_started_pod_with_retry()


def _min_replicas_available(deployment):
    return (deployment is not None and
            deployment.status.available_replicas is not None and
            deployment.status.available_replicas > 0)


def wait_for_deployment_minimum_replicas_available(
    k8s_client,
    namespace,
    deployment: client.V1Deployment,
    timeout_sec=60,
    wait_sec=1
) -> client.V1Deployment:
    if _min_replicas_available(deployment):
        return deployment

    @retrying.retry(retry_on_result=lambda r: not _min_replicas_available(r),
                    stop_max_delay=timeout_sec * 1000,
                    wait_fixed=wait_sec * 1000)
    def _get_deployment_with_retry():
        updated_deployment = get_deployment_by_name(k8s_client, namespace,
                                                    deployment.metadata.name)
        logger.info('Waiting for deployment %s replicas, current count %s',
                    updated_deployment.metadata.name,
                    updated_deployment.status.available_replicas)
        return updated_deployment

    return _get_deployment_with_retry()


def wait_for_deployment_deleted(
    k8s_client,
    namespace,
    deployment: client.V1Deployment,
    timeout_sec=60,
    wait_sec=1
) -> client.V1Deployment:
    @retrying.retry(retry_on_result=_min_replicas_available,
                    stop_max_delay=timeout_sec * 1000,
                    wait_fixed=wait_sec * 1000)
    def _wait_for_deleted_deployment_with_retry():
        deleted_deployment = get_deployment_by_name(k8s_client, namespace,
                                                    deployment.metadata.name)
        if deleted_deployment:
            logger.info('Waiting for deployment %s to be deleted, current '
                        'replica count %s',
                        deleted_deployment.metadata.name,
                        deleted_deployment.status.available_replicas)
        return deleted_deployment

    return _wait_for_deleted_deployment_with_retry()


@simple_resource_get
def get_deployment_by_name(k8s_client, namespace,
                           deployment_name) -> client.V1Deployment:
    api_apps = client.AppsV1Api(k8s_client)
    return api_apps.read_namespaced_deployment(deployment_name, namespace)


def delete_deployment(k8s_client, namespace, deployment_name,
                      grace_period_seconds=5):
    api_apps = client.AppsV1Api(k8s_client)
    result = api_apps.delete_namespaced_deployment(
        name=deployment_name, namespace=namespace,
        body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=grace_period_seconds))

    # logger.info('del %s', result)


def apply_manifest(k8s_client, manifest, namespace):
    return utils.create_from_dict(k8s_client, manifest, namespace=namespace)


def _debug(k8s_obj):
    print(yaml.dump(k8s_obj.to_dict()))
