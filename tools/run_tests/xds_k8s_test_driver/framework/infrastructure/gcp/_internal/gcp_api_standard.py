#  Copyright 2021 gRPC authors.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import abc
import logging
from typing import Optional

from googleapiclient import discovery
import googleapiclient.errors

from framework.infrastructure import gcp
from framework.infrastructure.gcp._internal import gcp_api

logger = logging.getLogger(__name__)


class GcpApiStandard(gcp_api.GcpApiBase, metaclass=abc.ABCMeta):
    GLOBAL_LOCATION = 'global'

    def parent(self, location: Optional[str] = GLOBAL_LOCATION):
        if location is None:
            location = self.GLOBAL_LOCATION
        return f'projects/{self.project}/locations/{location}'

    def resource_full_name(self, name, collection_name):
        return f'{self.parent()}/{collection_name}/{name}'

    def _create_resource(self, collection: discovery.Resource, body: dict,
                         **kwargs):
        logger.info("Creating %s resource:\n%s", self.api_name,
                    self._resource_pretty_format(body))
        create_req = collection.create(parent=self.parent(),
                                       body=body,
                                       **kwargs)
        self._execute(create_req)

    @property
    @abc.abstractmethod
    def api_name(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def api_version(self) -> str:
        raise NotImplementedError

    def _get_resource(self, collection: discovery.Resource, full_name):
        resource = collection.get(name=full_name).execute()
        logger.info('Loaded %s:\n%s', full_name,
                    self._resource_pretty_format(resource))
        return resource

    def _delete_resource(self, collection: discovery.Resource,
                         full_name: str) -> bool:
        logger.debug("Deleting %s", full_name)
        try:
            self._execute(collection.delete(name=full_name))
            return True
        except googleapiclient.errors.HttpError as error:
            if error.resp and error.resp.status == 404:
                logger.info('%s not deleted since it does not exist', full_name)
            else:
                logger.warning('Failed to delete %s, %r', full_name, error)
        return False

    def _execute(self,
                 request,
                 timeout_sec=gcp_api.GcpApiBase._WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=self._GCP_API_RETRIES)
        self._wait(operation, timeout_sec)

    def _wait(self,
              operation,
              timeout_sec=gcp_api.GcpApiBase._WAIT_FOR_OPERATION_SEC):
        op_name = operation['name']
        logger.debug('Waiting for %s operation, timeout %s sec: %s',
                     self.api_name, timeout_sec, op_name)

        op_request = self.api_client.projects().locations().operations().get(
            name=op_name)
        operation = self.wait_for_operation(
            operation_request=op_request,
            test_success_fn=lambda result: result['done'],
            timeout_sec=timeout_sec)

        logger.debug('Completed operation: %s', operation)
        if 'error' in operation:
            raise gcp.GcpOperationError(self.api_name, operation)
