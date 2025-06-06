// Copyright 2025 The gRPC Authors
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

#include "src/core/lib/event_engine/posix_engine/file_descriptor_collection.h"

#include <gmock/gmock.h>
#include <grpc/grpc.h>
#include <gtest/gtest.h>

#include "src/core/lib/experiments/experiments.h"

namespace grpc_event_engine::experimental {

bool ForkEnabled() {
#ifndef GRPC_ENABLE_FORK_SUPPORT
  return false;
#else
  return grpc_core::IsEventEngineForkEnabled();
#endif
}

TEST(FileDescriptorCollection, AddRecordsGenerationClearClears) {
  FileDescriptorCollection collection(42);
  EXPECT_EQ(collection.Add(10), FileDescriptor(10, 42));
  EXPECT_EQ(collection.Add(12), FileDescriptor(12, 42));
  if (ForkEnabled()) {
    EXPECT_THAT(collection.ClearAndReturnRawDescriptors(),
                ::testing::UnorderedElementsAre(10, 12));
  } else {
    EXPECT_THAT(collection.ClearAndReturnRawDescriptors(),
                ::testing::IsEmpty());
  }
}

TEST(FileDescriptorCollectionTest, RemoveHonorsGeneration) {
  FileDescriptorCollection collection(2);
  collection.Add(7);
  // Untracked
  EXPECT_EQ(collection.Remove(FileDescriptor(6, 2)), !ForkEnabled());
  // Wrong generation
  EXPECT_EQ(collection.Remove(FileDescriptor(7, 1)), !ForkEnabled());
  // Correct
  EXPECT_TRUE(collection.Remove(FileDescriptor(7, 2)));
  // Already gone
  EXPECT_EQ(collection.Remove(FileDescriptor(7, 2)), !ForkEnabled());
}

}  // namespace grpc_event_engine::experimental

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}