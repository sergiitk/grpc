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

import contextlib
import logging
import pathlib

import mako.template
import yaml

from infrastructure import k8s

logger = logging.getLogger()


class RunnerError(Exception):
    """Error running app"""


class KubernetesBaseRunner:
    k8s_namespace: k8s.KubernetesNamespace

    def __init__(self, k8s_namespace):
        # Kubernetes namespaced resources manager
        self.k8s_namespace = k8s_namespace

    def run(self, **kwargs):
        raise NotImplementedError('Must be overridden')

    def cleanup(self):
        raise NotImplementedError('Must be overridden')

    @staticmethod
    def _render_template(template_file, **kwargs):
        template = mako.template.Template(filename=str(template_file))
        return template.render(**kwargs)

    @staticmethod
    def _manifests_from_yaml_file(yaml_file):
        # Parse yaml
        with open(yaml_file) as f:
            with contextlib.closing(yaml.safe_load_all(f)) as yml:
                for manifest in yml:
                    yield manifest

    @staticmethod
    def _manifests_from_str(document):
        with contextlib.closing(yaml.safe_load_all(document)) as yml:
            for manifest in yml:
                yield manifest

    @staticmethod
    def _template_file_from_name(template_name):
        templates_path = pathlib.Path(__file__).parent / '../templates'
        return templates_path.joinpath(template_name).absolute()

    def _create_from_template(self, template_name, **kwargs):
        template_file = self._template_file_from_name(template_name)
        logger.info("Loading template: %s", template_file)

        yaml_doc = self._render_template(template_file, **kwargs)
        logger.info("Rendered template:\n%s\n", yaml_doc)

        manifests = self._manifests_from_str(yaml_doc)
        manifest = next(manifests)
        # Error out on multi-document yaml
        if next(manifests, False):
            raise RunnerError('Exactly one document expected in manifest '
                              f'{template_file}')
        # Apply the manifest
        k8s_objects = self.k8s_namespace.apply_manifest(manifest)

        # Check correctness
        if len(k8s_objects) != 1:
            raise RunnerError('Expected exactly one object must created from '
                              f'manifest {template_file}')

        logger.info('%s %s created', k8s_objects[0].kind,
                    k8s_objects[0].metadata.name)

        return k8s_objects[0]

    def _reuse_deployment(self, deployment_name) -> k8s.V1Deployment:
        deployment = self.k8s_namespace.get_deployment(deployment_name)
        # todo(sergiitk): check if good or must be recreated
        return deployment

    def _create_deployment(self, template, **kwargs) -> k8s.V1Deployment:
        deployment = self._create_from_template(template, **kwargs)
        if not isinstance(deployment, k8s.V1Deployment):
            raise RunnerError('Expected V1Deployment to be created '
                              f'from manifest {template}')

        if deployment.metadata.name != kwargs['deployment_name']:
            raise RunnerError(
                'Deployment created with unexpected name: '
                f'{deployment.metadata.name}')

        logger.info('Deployment %s created at %s',
                    deployment.metadata.self_link,
                    deployment.metadata.creation_timestamp)

        return deployment

    def _delete_deployment(self, deployment_name, wait_for_deletion=True):
        self.k8s_namespace.delete_deployment(deployment_name)
        if wait_for_deletion:
            self.k8s_namespace.wait_for_deployment_deleted(deployment_name)
        logger.info('Deployment %s deleted', deployment_name)

    def _get_deployment_with_available_replicas(self, name, count: int = 1):
        self.k8s_namespace.wait_for_deployment_available_replicas(name, count)
        deployment = self.k8s_namespace.get_deployment(name)
        logger.info('Deployment %s has %i replicas available',
                    deployment.metadata.name,
                    deployment.status.available_replicas)
        return deployment

    def _get_pod_started(self, pod_name) -> k8s.V1Pod:
        self.k8s_namespace.wait_for_pod_started(pod_name)
        pod = self.k8s_namespace.get_pod(pod_name)
        logger.info('Pod %s ready, IP: %s', pod.metadata.name,
                    pod.status.pod_ip)
        return pod
