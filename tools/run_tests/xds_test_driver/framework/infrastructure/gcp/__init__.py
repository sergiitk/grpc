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
import functools
import logging
import os

from googleapiclient import discovery
import retrying

logger = logging.getLogger(__name__)


class GcpApiManager:
    def __init__(self, alpha_api_key=None):
        self.alpha_api_key = alpha_api_key or os.getenv('ALPHA_API_KEY')

    @functools.lru_cache(None)
    def compute(self, version):
        api_name = 'compute'
        if version == 'v1':
            return discovery.build(api_name, version, cache_discovery=False)
        raise NotImplementedError(f'Compute {version} not supported')

    @functools.lru_cache(None)
    def networksecurity(self, version):
        api_name = 'networksecurity'

        if version == 'v1alpha1':
            return discovery.build(
                api_name, version,
                discoveryServiceUrl=f'{discovery.V2_DISCOVERY_URI}'
                                    f'{self._key_param(self.alpha_api_key)}',
                cache_discovery=False)

        raise NotImplementedError(f'Network Security {version} not supported')

    @functools.lru_cache(None)
    def networkservices(self, version):
        api_name = 'networkservices'

        if version == 'v1alpha1':
            return discovery.build(
                api_name, version,
                discoveryServiceUrl=f'{discovery.V2_DISCOVERY_URI}'
                                    f'{self._key_param(self.alpha_api_key)}',
                cache_discovery=False)

        raise NotImplementedError(f'Network Services {version} not supported')

    @staticmethod
    def _key_param(key):
        return f'&key={key}' if key else ''

    def close(self):
        """todo(sergiitk): contextlib exitstack"""
        # if self._compute_v1:
        #     self._compute_v1.close()


class GcpProjectApiResource:
    # todo(sergiitk): move someplace better
    _WAIT_FOR_OPERATION_SEC = 1200
    _WAIT_FIXES_SEC = 2

    def __init__(self, api: discovery.Resource, project: str):
        self.api: discovery.Resource = api
        self.project: str = project

    @staticmethod
    def wait_for_operation(operation_request,
                           test_success_fn,
                           timeout_sec=_WAIT_FOR_OPERATION_SEC,
                           wait_sec=_WAIT_FIXES_SEC):
        @retrying.retry(
            retry_on_result=lambda result: not test_success_fn(result),
            stop_max_delay=timeout_sec * 1000,
            wait_fixed=wait_sec * 1000)
        def _retry_until_status_done():
            logger.debug('Waiting for operation...')
            return operation_request.execute()

        return _retry_until_status_done()
