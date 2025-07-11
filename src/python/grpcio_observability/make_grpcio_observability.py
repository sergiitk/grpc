#!/usr/bin/env python3

# Copyright 2023 gRPC authors.
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

import errno
import os
import os.path
import pprint
import shutil
import subprocess
import sys
import traceback

# the template for the content of observability_lib_deps.py
DEPS_FILE_CONTENT = """
# Copyright 2023 gRPC authors.
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

# AUTO-GENERATED BY make_grpcio_observability.py!
CC_FILES={cc_files}

CC_INCLUDES={cc_includes}
"""

# maps bazel reference to actual path
BAZEL_REFERENCE_LINK = [
    ("@com_google_absl//", "third_party/abseil-cpp/"),
    ("//src", "grpc_root/src"),
]

ABSL_INCLUDE = (os.path.join("third_party", "abseil-cpp"),)
UPB_GEN_INCLUDE = (os.path.join("grpc_root", "src", "core", "ext", "upb-gen"),)
UPB_DEFS_GEN_INCLUDE = (
    os.path.join("grpc_root", "src", "core", "ext", "upbdefs-gen"),
)
PROTOBUF_INCLUDE = (os.path.join("third_party", "protobuf"),)

# will be added to include path when building grpcio_observability
EXTENSION_INCLUDE_DIRECTORIES = (
    ABSL_INCLUDE + UPB_GEN_INCLUDE + UPB_DEFS_GEN_INCLUDE + PROTOBUF_INCLUDE
)

CC_INCLUDES = list(EXTENSION_INCLUDE_DIRECTORIES)

# the target directory is relative to the grpcio_observability package root.
GRPCIO_OBSERVABILITY_ROOT_PREFIX = "src/python/grpcio_observability/"

# Pairs of (source, target) directories to copy
# from the grpc repo root to the grpcio_observability build root.
COPY_FILES_SOURCE_TARGET_PAIRS = [
    ("include", "grpc_root/include"),
    ("third_party/abseil-cpp/absl", "third_party/abseil-cpp/absl"),
    ("third_party/protobuf/upb", "third_party/protobuf/upb"),
    ("src/core", "grpc_root/src/core"),
]

# grpc repo root
GRPC_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)


# the file to generate
GRPC_PYTHON_OBSERVABILITY_LIB_DEPS = os.path.join(
    GRPC_ROOT,
    "src",
    "python",
    "grpcio_observability",
    "observability_lib_deps.py",
)

# the script to run for getting dependencies
BAZEL_DEPS = os.path.join(
    GRPC_ROOT, "tools", "distrib", "python", "bazel_deps.sh"
)

# the bazel target to scrape to get list of sources for the build
BAZEL_DEPS_QUERIES = [
    "//src/core:experiments",
    "//src/core:slice",
    "//src/core:ref_counted_string",
]


def _bazel_query(query):
    """Runs 'bazel query' to collect source file info."""
    print('Running "bazel query %s"' % query)
    output = subprocess.check_output([BAZEL_DEPS, query])
    return output.decode("ascii").splitlines()


def _pretty_print_list(items):
    """Pretty print python list"""
    formatted = pprint.pformat(items, indent=4)
    # add newline after opening bracket (and fix indent of the next line)
    if formatted.startswith("["):
        formatted = formatted[0] + "\n " + formatted[1:]
    # add newline before closing bracket
    if formatted.endswith("]"):
        formatted = formatted[:-1] + "\n" + formatted[-1]
    return formatted


def _bazel_name_to_file_path(name):
    """Transform bazel reference to source file name."""
    for link in BAZEL_REFERENCE_LINK:
        if name.startswith(link[0]):
            filepath = link[1] + name[len(link[0]) :].replace(":", "/")
            return filepath
    return None


def _generate_deps_file_content():
    """Returns the data structure with dependencies of protoc as python code."""
    cc_files_output = []
    for query in BAZEL_DEPS_QUERIES:
        cc_files_output += _bazel_query(query)

    # Collect .cc files (that will be later included in the native extension build)
    cc_files = set()
    for name in cc_files_output:
        if name.endswith(".cc"):
            filepath = _bazel_name_to_file_path(name)
            if filepath:
                cc_files.add(filepath)

    deps_file_content = DEPS_FILE_CONTENT.format(
        cc_files=_pretty_print_list(sorted(list(cc_files))),
        cc_includes=_pretty_print_list(CC_INCLUDES),
    )
    return deps_file_content


def _copy_source_tree(source, target):
    """Copies source directory to a given target directory."""
    print("Copying contents of %s to %s" % (source, target))
    for source_dir, _, files in os.walk(source):
        target_dir = os.path.abspath(
            os.path.join(target, os.path.relpath(source_dir, source))
        )
        try:
            os.makedirs(target_dir)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise
        for relative_file in files:
            source_file = os.path.abspath(
                os.path.join(source_dir, relative_file)
            )
            target_file = os.path.abspath(
                os.path.join(target_dir, relative_file)
            )
            shutil.copyfile(source_file, target_file)


def main():
    os.chdir(GRPC_ROOT)

    # Step 1:
    # In order to be able to build the grpcio_observability package, we need the source
    # code for the plugins and its dependencies to be available under the build root of
    # the grpcio_observability package.
    # So we simply copy all the necessary files where the build will expect them to be.
    for source, target in COPY_FILES_SOURCE_TARGET_PAIRS:
        # convert the slashes in the relative path to platform-specific path dividers.
        # All paths are relative to GRPC_ROOT
        source_abs = os.path.join(GRPC_ROOT, os.path.join(*source.split("/")))
        # for targets, add grpcio_observability root prefix
        target = GRPCIO_OBSERVABILITY_ROOT_PREFIX + target
        target_abs = os.path.join(GRPC_ROOT, os.path.join(*target.split("/")))
        _copy_source_tree(source_abs, target_abs)
    print(
        "The necessary source files were copied under the grpcio_observability package root."
    )

    # Step 2:
    # Extract build metadata from bazel build (by running "bazel query")
    # and populate the observability_lib_deps.py file with python-readable data structure
    # that will be used by grpcio_observability's setup.py.
    try:
        print('Invoking "bazel query" to gather the dependencies.')
        observability_lib_deps_content = _generate_deps_file_content()
    except Exception as error:
        # We allow this script to succeed even if we couldn't get the dependencies,
        # as then we can assume that even without a successful bazel run the
        # dependencies currently in source control are 'good enough'.
        sys.stderr.write("Got non-fatal error:\n")
        traceback.print_exc(file=sys.stderr)
        return
    # If we successfully got the dependencies, truncate and rewrite the deps file.
    with open(GRPC_PYTHON_OBSERVABILITY_LIB_DEPS, "w") as deps_file:
        deps_file.write(observability_lib_deps_content)
    print('File "%s" updated.' % GRPC_PYTHON_OBSERVABILITY_LIB_DEPS)
    print("Done.")


if __name__ == "__main__":
    main()
