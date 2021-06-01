# Copyright 2021 gRPC authors.
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

from googleapiclient import discovery
import tenacity
import yaml

logger = logging.getLogger(__name__)


class GcpApiError(Exception):
    """Base error class for GCP API errors"""


class GcpApiBase(metaclass=abc.ABCMeta):
    # TODO(sergiitk): move someplace better
    _WAIT_FOR_OPERATION_SEC = 60 * 5
    _WAIT_FIXED_SEC = 2
    _GCP_API_RETRIES = 5

    def __init__(self, api_client: discovery.Resource, project: str):
        self.api_client: discovery.Resource = api_client
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
