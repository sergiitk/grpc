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
"""Base test case used for xds test suites."""

import logging
import unittest
from typing import Optional

from absl.testing import absltest

import absl.testing.xml_reporter

logger = logging.getLogger(__name__)


class BaseTestCase(absltest.TestCase):
    def run(self, result: unittest.TestResult = None) -> None:
        result = super().run(result)
        return

        current_errors = [
            error for test, error in result.errors if test is self
        ]
        current_failures = [
            failure for test, failure in result.failures if test is self
        ]
        current_unexpected_successes = [
            test for test in result.unexpectedSuccesses if test is self
        ]
        current_skipped = next(
            (reason for test, reason in result.skipped if test is self),
            None,
        )
        # Assume one test case will only have one status.
        if current_errors or current_failures:
            logging.info("----- TestCase %s FAILED -----", self.id())
            if current_errors:
                self._print_error_list(current_errors, is_unexpected_error=True)
            if current_failures:
                self._print_error_list(current_failures)
        elif current_unexpected_successes:
            logging.info(
                "----- TestCase %s UNEXPECTEDLY SUCCEED -----", self.id()
            )
        elif current_skipped:
            logging.info("----- TestCase %s SKIPPED -----", self.id())
            logging.info("Reason for skipping: %s", current_skipped)
        else:
            logging.info("----- TestCase %s PASSED -----", self.id())

    def _print_error_list(
        self, errors: Optional[list[str]], is_unexpected_error: bool = False
    ) -> None:
        # FAILUREs are those errors explicitly signalled using
        # the TestCase.assert*() methods.
        for err in errors:
            logging.error(
                "%s Traceback in %s:\n%s",
                "ERROR" if is_unexpected_error else "FAILURE",
                self.id(),
                err,
            )


class CustomTextAndXMLTestResult(
    absl.testing.xml_reporter._TextAndXMLTestResult
):
    def addError(self, test, err):
        print(11111)
        logger.info("----- TestCase %s FAILED -----", test.id())
        logger.error("ERROR Traceback in %s:\n%r", test.id(), err)
        super().addError(test, err)

    def addFailure(self, test, err):
        print(11111)
        logger.info("----- TestCase %s FAILED -----", test.id())
        logger.error("Failure Traceback in %s:\n%r", test.id(), err)
        super().addFailure(test, err)


# Monkey patch the default report class
absl.testing.xml_reporter.TextAndXMLTestRunner._TEST_RESULT_CLASS = (
    CustomTextAndXMLTestResult
)
