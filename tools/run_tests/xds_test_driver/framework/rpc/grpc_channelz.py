#  Copyright 2020 gRPC authors.
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
import logging
from typing import Optional, Iterator

import grpc
from grpc_channelz.v1 import channelz_pb2
from grpc_channelz.v1 import channelz_pb2_grpc

import framework.rpc

logger = logging.getLogger(__name__)

# Type aliases
Channel = channelz_pb2.Channel
ChannelConnectivityState = channelz_pb2.ChannelConnectivityState
GetTopChannelsRequest = channelz_pb2.GetTopChannelsRequest
GetTopChannelsResponse = channelz_pb2.GetTopChannelsResponse


class ChannelzServiceClient(framework.rpc.GrpcClientHelper):
    stub: channelz_pb2_grpc.ChannelzStub

    def __init__(self, channel: grpc.Channel):
        super().__init__(channel, channelz_pb2_grpc.ChannelzStub)

    def find_channels_for_target(self, target: str) -> Iterator[Channel]:
        return (channel for channel in self.list_channels()
                if channel.data.target == target)

    def list_channels(self) -> Iterator[Channel]:
        """
        Lists all root channels (i.e. channels the application has directly
        created). This does not include subchannels nor non-top level channels.
        """
        start: int = -1
        response: Optional[GetTopChannelsResponse] = None
        while start < 0 or not response.end:
            # From proto: To request subsequent pages, the client generates this
            # value by adding 1 to the highest seen result ID.
            start += 1
            response = self.call_unary_when_channel_ready(
                rpc='GetTopChannels',
                request=GetTopChannelsRequest(start_channel_id=start))
            for channel in response.channel:
                start = max(start, channel.ref.channel_id)
                yield channel
