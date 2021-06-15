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
import functools
import logging

import dataclasses
from typing import List, Optional, FrozenSet

from framework.infrastructure import gcp

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ServiceAccount:
    """An IAM service account.

    https://cloud.google.com/iam/docs/reference/rest/v1/projects
    .serviceAccounts#ServiceAccount
    Note: "etag" field is skipped because it's deprecated
    """
    name: str
    projectId: str
    uniqueId: str
    email: str
    oauth2ClientId: str
    displayName: str = ''
    description: str = ''
    disabled: bool = False

    @classmethod
    def from_response(cls, response):
        return cls(name=response['name'],
                   projectId=response['projectId'],
                   uniqueId=response['uniqueId'],
                   email=response['email'],
                   oauth2ClientId=response['oauth2ClientId'],
                   description=response.get('description', ''),
                   displayName=response.get('displayName', ''),
                   disabled=response.get('disabled', False))

    def as_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Expr:
    """
    Represents a textual expression in the Common Expression Language syntax.

    https://cloud.google.com/iam/docs/reference/rest/v1/Expr
    """
    expression: str
    title: str = ''
    description: str = ''
    location: str = ''

    @classmethod
    def from_response(cls, response):
        return cls(**response)

    def as_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass(eq=False, frozen=True)
class Policy:
    """An Identity and Access Management (IAM) policy, which specifies
    access controls for Google Cloud resources.

    https://cloud.google.com/iam/docs/reference/rest/v1/Policy
    Note: auditConfigs not supported by this implementation.
    """

    @dataclasses.dataclass(frozen=True)
    class Binding:
        """Policy Binding. Associates members with a role.

        https://cloud.google.com/iam/docs/reference/rest/v1/Policy#binding
        """
        role: str
        members: FrozenSet[str]
        condition: Optional[Expr] = None

        @classmethod
        def from_response(cls, response):
            fields = {
                'role': response['role'],
                'members': frozenset(response.get('members', [])),
            }
            if 'condition' in response:
                fields['condition'] = Expr.from_response(response['condition'])

            return cls(**fields)

        def as_dict(self):
            if self.condition is not None:
                condition = self.condition.as_dict()
            else:
                condition = {}
            return {
                'role': self.role,
                'members': list(self.members),
                'condition': condition,
            }

    bindings: List[Binding]
    etag: str
    version: Optional[int] = None

    @functools.lru_cache(maxsize=128)
    def find_binding_for_role(self, role: str, condition: Expr = None):
        results = (binding for binding in self.bindings
                   if binding.role == role and binding.condition == condition)
        return next(results, None)

    @classmethod
    def from_response(cls, response):
        bindings = []
        if 'bindings' in response:
            for binding in response['bindings']:
                bindings.append(cls.Binding.from_response(binding))

        return cls(bindings=bindings,
                   etag=response['etag'],
                   version=response.get('version'))

    def as_dict(self):
        result = {
            'bindings': [binding.as_dict() for binding in self.bindings],
            'etag': self.etag,
        }
        if self.version is not None:
            result['version'] = self.version
        return result


class IamV1(gcp.api.GcpProjectApiResource):
    """
    Identity and Access Management (IAM) API

    https://cloud.google.com/iam/docs/reference/rest
    """

    # Operations that affect conditional role bindings must specify version 3.
    # Otherwise conditions are omitted, and role names returned with a suffix,
    # f.e. roles/iam.workloadIdentityUser_withcond_f1ec33c9beb41857dbf0
    # https://cloud.google.com/iam/docs/reference/rest/v1/Policy#FIELDS.version
    POLICY_VERSION: str = 3

    def __init__(self, api_manager: gcp.api.GcpApiManager, project: str):
        super().__init__(api_manager.iam('v1'), project)
        # Shortcut to projects/*/serviceAccounts/ endpoints
        self._service_accounts = self.api.projects().serviceAccounts()

    def service_account_resource_name(self, account):
        """
        Returns full resource name of the service account.

        The resource name of the service account in the following format:
        projects/{PROJECT_ID}/serviceAccounts/{ACCOUNT}.
        The ACCOUNT value can be the email address or the uniqueId of the
        service account.
        Ref https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts/get

        Args:
            account: The ACCOUNT value
        """
        return f'projects/{self.project}/serviceAccounts/{account}'

    def get_service_account(self, account: str) -> ServiceAccount:
        response = self._service_accounts.get(
            name=self.service_account_resource_name(account)).execute()
        logger.debug('Loaded Service Account:\n%s',
                     self._resource_pretty_format(response))
        return ServiceAccount.from_response(response)

    def get_service_account_iam_policy(self, account: str) -> Policy:
        response = self._service_accounts.getIamPolicy(
            resource=self.service_account_resource_name(account),
            options_requestedPolicyVersion=self.POLICY_VERSION).execute()
        logger.debug('Loaded Service Account Policy:\n%s',
                     self._resource_pretty_format(response))
        return Policy.from_response(response)

    def add_service_account_iam_policy_binding(self, account: str, role: str,
                                               member: str) -> Policy:
        """Add an IAM policy binding to an IAM service account

        ❯ gcloud iam service-accounts add-iam-policy-binding

        '--role=roles/iam.workloadIdentityUser' --member
        'serviceAccount:sergiitk-grpc-gke.svc.id.goog[sergii-psm-test/test-app]'
        """
        # TODO(sergiitk): test add binding when no elements

        current_policy = self.get_service_account_iam_policy(account)
        # logger.info(current_policy)
        # binding = current_policy.find_binding_for_role(role)
        # binding.members.append(member)
        # logger.info(binding.members)
        logger.info(current_policy.as_dict())

        # current_policy.bindings.
        # response = self._service_accounts.getIamPolicy(
        #     resource=self.service_account_resource_name(account),
        #     options_requestedPolicyVersion=self.POLICY_VERSION).execute()
        # logger.debug('Loaded Service Account Policy:\n%s',
        #              self._resource_pretty_format(response))
        # return self.Policy.from_response(response)
