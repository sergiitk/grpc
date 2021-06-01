# Copyright 2020 gRPC authors.
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
import abc
import logging
from typing import Optional

# Workaround: `grpc` must be imported before `google.protobuf.json_format`,
# to prevent "Segmentation fault". Ref https://github.com/grpc/grpc/issues/24897
# TODO(sergiitk): Remove after #24897 is solved
import grpc  # noqa pylint: disable=unused-import
from google.longrunning import operations_pb2
from google.protobuf import json_format
from google.rpc import code_pb2
from googleapiclient import discovery
import googleapiclient.errors
import tenacity
import yaml

logger = logging.getLogger(__name__)

# Type aliases
Operation = operations_pb2.Operation


class Error(Exception):
    """Base error class for GCP API errors"""


class OperationError(Error):
    """
    Operation was not successful.

    Assuming Operation based on Google API Style Guide:
    https://cloud.google.com/apis/design/design_patterns#long_running_operations
    https://github.com/googleapis/googleapis/blob/master/google/longrunning/operations.proto
    """

    def __init__(self, api_name, operation_response, message=None):
        self.api_name = api_name
        operation = json_format.ParseDict(operation_response, Operation())
        self.name = operation.name or 'unknown'
        self.error = operation.error
        self.code_name = code_pb2.Code.Name(operation.error.code)
        if message is None:
            message = (f'{api_name} operation "{self.name}" failed. Error '
                       f'code: {self.error.code} ({self.code_name}), '
                       f'message: {self.error.message}')
        self.message = message
        super().__init__(message)


class GcpProjectApiResource:
    # TODO(sergiitk): move someplace better
    _WAIT_FOR_OPERATION_SEC = 60 * 5
    _WAIT_FIXED_SEC = 2
    _GCP_API_RETRIES = 5

    def __init__(self, api: discovery.Resource, project: str):
        self.api: discovery.Resource = api
        self.project: str = project

    @staticmethod
    def wait_for_operation(operation_request,
                           test_success_fn,
                           timeout_sec=_WAIT_FOR_OPERATION_SEC,
                           wait_sec=_WAIT_FIXED_SEC):
        retryer = tenacity.Retrying(
            retry=(tenacity.retry_if_not_result(test_success_fn) |
                   tenacity.retry_if_exception_type()),
            wait=tenacity.wait_fixed(wait_sec),
            stop=tenacity.stop_after_delay(timeout_sec),
            after=tenacity.after_log(logger, logging.DEBUG),
            reraise=True)
        return retryer(operation_request.execute)

    @staticmethod
    def _resource_pretty_format(body: dict) -> str:
        """Return a string with pretty-printed resource body."""
        return yaml.dump(body, explicit_start=True, explicit_end=True)


class GcpStandardCloudApiResource(GcpProjectApiResource, metaclass=abc.ABCMeta):
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
                 timeout_sec=GcpProjectApiResource._WAIT_FOR_OPERATION_SEC):
        operation = request.execute(num_retries=self._GCP_API_RETRIES)
        self._wait(operation, timeout_sec)

    def _wait(self,
              operation,
              timeout_sec=GcpProjectApiResource._WAIT_FOR_OPERATION_SEC):
        op_name = operation['name']
        logger.debug('Waiting for %s operation, timeout %s sec: %s',
                     self.api_name, timeout_sec, op_name)

        op_request = self.api.projects().locations().operations().get(
            name=op_name)
        operation = self.wait_for_operation(
            operation_request=op_request,
            test_success_fn=lambda result: result['done'],
            timeout_sec=timeout_sec)

        logger.debug('Completed operation: %s', operation)
        if 'error' in operation:
            raise OperationError(self.api_name, operation)
