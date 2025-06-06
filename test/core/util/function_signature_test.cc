// Copyright 2025 gRPC authors.
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

#include "src/core/util/function_signature.h"

#include "gmock/gmock.h"
#include "gtest/gtest.h"

namespace grpc_core {

namespace {
class Foo {};
}  // namespace

TEST(FunctionSignatureTest, Works) {
  if (TypeName<int>() == "unknown") {
    GTEST_SKIP() << "insufficient support for this platform";
  }
  EXPECT_EQ(TypeName<int>(), "int");
  EXPECT_THAT(TypeName<Foo>(), ::testing::HasSubstr("Foo"));
  auto x = []() {};
  EXPECT_THAT(TypeName<decltype(x)>(), ::testing::HasSubstr("lambda"));
}

}  // namespace grpc_core
