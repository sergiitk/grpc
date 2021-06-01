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
"""Handles Long Running Operations (LRO)

https://cloud.google.com/apis/design/design_patterns#long_running_operations
https://github.com/googleapis/googleapis/blob/master/google/longrunning/operations.proto
"""

from google.protobuf import json_format
from google.rpc import code_pb2
from google.longrunning import operations_pb2

from framework.infrastructure.gcp._internal.gcp_api import GcpApiError

# Type aliases
Operation = operations_pb2.Operation


class GcpOperationError(GcpApiError):
    """Long Running Operation was not successful."""

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
