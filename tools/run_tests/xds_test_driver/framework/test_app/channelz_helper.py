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
from typing import Optional

import grpc
from grpc_channelz.v1 import channelz_pb2
from grpc_channelz.v1 import channelz_pb2_grpc

from framework.test_app import grpc_helper

logger = logging.getLogger(__name__)

GRPC_REQUEST_TIMEOUT_SEC = 1200
GRPC_CONNECTION_TIMEOUT_SEC = 60

# Type aliases
Channel = channelz_pb2.Channel
ChannelzStub = channelz_pb2_grpc.ChannelzStub
GetTopChannelsRequest = channelz_pb2.GetTopChannelsRequest
GetTopChannelsResponse = channelz_pb2.GetTopChannelsResponse


class NoMatchingChannel(Exception):
    """Channel matching requested conditions not found"""


def get_channel_with_target(ch: grpc.Channel, target: str) -> Channel:
    for channel in list_channels(ch):
        if channel.data.target == target:
            return channel
    raise NoMatchingChannel


def list_channels(ch: grpc.Channel):
    stub = ChannelzStub(ch)
    start: int = -1
    response: Optional[GetTopChannelsResponse] = None
    while start < 0 or not response.end:
        # From proto: To request subsequent pages, the client generates this
        # value by adding 1 to the highest seen result ID.
        start += 1
        logger.debug('Requesting GetTopChannels(start_channel_id=%s)', start)
        response = grpc_helper.call_unary_when_ready(
            stub.GetTopChannels, GetTopChannelsRequest(start_channel_id=start))

        for channel in response.channel:
            start = max(start, channel.ref.channel_id)
            yield channel
