//
//
// Copyright 2017 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
//

#include "src/core/channelz/zviz/strings.h"

#include "fuzztest/fuzztest.h"
#include "gtest/gtest.h"

namespace grpc_zviz {

TEST(StringsTest, DisplayKind) {
  EXPECT_EQ(DisplayKind("channel"), "Channel");
  EXPECT_EQ(DisplayKind("subchannel"), "Subchannel");
  EXPECT_EQ(DisplayKind("socket"), "Socket");
  EXPECT_EQ(DisplayKind("foo"), "Entity kind 'foo'");
  EXPECT_EQ(DisplayKind(""), "Entity");
}

void DisplayKindNeverEmpty(absl::string_view kind) {
  EXPECT_NE(DisplayKind(kind), "");
}
FUZZ_TEST(StringsTest, DisplayKindNeverEmpty);

}  // namespace grpc_zviz
