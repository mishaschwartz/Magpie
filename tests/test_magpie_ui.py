#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_magpie_ui
----------------------------------

Tests for :mod:`magpie.ui` module.
"""

import unittest

# NOTE: must be imported without 'from', otherwise the interface's test cases are also executed
import tests.interfaces as ti
from magpie.constants import get_constant
from magpie.models import Route
from magpie.services import ServiceAPI, ServiceWPS
from tests import runner, utils


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_LOCAL
class TestCase_MagpieUI_NoAuth_Local(ti.Interface_MagpieUI_NoAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that do not require any AuthN/AuthZ (``MAGPIE_ANONYMOUS_GROUP`` & ``MAGPIE_ANONYMOUS_USER``).

    Use a local Magpie test application.
    """

    __test__ = True

    @classmethod
    def setUpClass(cls):
        cls.app = utils.get_test_magpie_app()
        cls.url = cls.app  # to simplify calls of TestSetup (all use .url)
        cls.cookies = None
        # note: admin credentials to setup data on test instance as needed, but not to be used for these tests
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.setup_admin()
        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-no-auth_ui-user-local",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-no-auth_ui-group-local",
                                           raise_missing=False, raise_not_set=False)
        cls.test_service_type = ServiceWPS.service_type
        cls.test_service_name = "magpie-unittest-service-wps"


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_LOCAL
class TestCase_MagpieUI_UsersAuth_Local(ti.Interface_MagpieUI_UsersAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that require logged user AuthN/AuthZ, but lower than ``MAGPIE_ADMIN_GROUP``.

    Use a local Magpie test application.
    """

    __test__ = True

    @classmethod
    def setUpClass(cls):
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.app = utils.get_test_magpie_app()
        cls.url = cls.app  # to simplify calls of TestSetup (all use .url)
        cls.version = utils.TestSetup.get_Version(cls)
        cls.setup_admin()
        cls.check_requirements()
        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-user-auth_ui-user-local",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-user-auth_ui-group-local",
                                           raise_missing=False, raise_not_set=False)


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_LOCAL
class TestCase_MagpieUI_AdminAuth_Local(ti.Interface_MagpieUI_AdminAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that require at least ``MAGPIE_ADMIN_GROUP`` AuthN/AuthZ.

    Use a local Magpie test application.
    """

    __test__ = True

    @classmethod
    def setUpClass(cls):
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.app = utils.get_test_magpie_app()
        cls.url = cls.app  # to simplify calls of TestSetup (all use .url)
        cls.cookies = None
        cls.version = utils.TestSetup.get_Version(cls)
        cls.headers, cls.cookies = utils.check_or_try_login_user(cls.url, cls.usr, cls.pwd, use_ui_form_submit=True)
        cls.require = "cannot run tests without logged in user with '{}' permissions".format(cls.grp)
        cls.setup_admin()
        cls.check_requirements()

        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-admin-auth_ui-user-local",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-admin-auth_ui-group-local",
                                           raise_missing=False, raise_not_set=False)
        cls.test_service_type = ServiceAPI.service_type
        cls.test_service_name = "magpie-unittest-ui-admin-local-service"

        cls.test_service_parent_resource_type = ServiceAPI.service_type
        cls.test_service_parent_resource_name = "magpie-unittest-ui-tree-parent"
        cls.test_service_child_resource_type = Route.resource_type_name
        cls.test_service_child_resource_name = "magpie-unittest-ui-tree-child"

    @runner.MAGPIE_TEST_LOCAL   # not implemented for remote URL
    @runner.MAGPIE_TEST_STATUS
    @runner.MAGPIE_TEST_FUNCTIONAL
    def test_EditService_Goto_AddChild_BackTo_EditService(self):
        """
        Verifies that UI button redirects work for the workflow:
            0. Starting on "Service View", press "Add Child" button (redirects to "New Resource" form)
            1. Fill form and press "Add" button (creates the service resource and redirects to "Service View")
            2. Back on "Service View", <new-resource> is visible in the list.

        Note:
            Only implemented locally with form submission of ``TestApp``.
        """
        try:
            # make sure any sub-resource are all deleted to avoid conflict, then recreate service to add sub-resource
            utils.TestSetup.delete_TestService(self, override_service_name=self.test_service_parent_resource_name)
            body = utils.TestSetup.create_TestService(self,
                                                      override_service_name=self.test_service_parent_resource_name,
                                                      override_service_type=self.test_service_parent_resource_type)
            svc_res_id = body["service"]["resource_id"]
            form = {"add_child": None, "resource_id": str(svc_res_id)}
            path = "/ui/services/{}/{}".format(self.test_service_parent_resource_type,
                                               self.test_service_parent_resource_name)
            resp = utils.TestSetup.check_FormSubmit(self, form_match=form, form_submit="add_child", path=path)
            utils.check_val_is_in("New Resource", resp.text, msg=utils.null)    # add resource page reached
            data = {
                "resource_name": self.test_service_child_resource_name,
                "resource_type": self.test_service_child_resource_type,
            }
            resp = utils.TestSetup.check_FormSubmit(self, form_match="add_resource_form", form_submit="add_child",
                                                    form_data=data, previous_response=resp)
            for res_name in (self.test_service_parent_resource_name, self.test_service_child_resource_name):
                find = "<div class=\"tree-item\">{}</div>".format(res_name)
                utils.check_val_is_in(find, resp.text, msg=utils.null)
        finally:
            utils.TestSetup.delete_TestService(self, override_service_name=self.test_service_parent_resource_name)


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_REMOTE
class TestCase_MagpieUI_NoAuth_Remote(ti.Interface_MagpieUI_NoAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that do not require any AuthN/AuthZ (``MAGPIE_ANONYMOUS_GROUP`` & ``MAGPIE_ANONYMOUS_USER``).

    Use an already running remote bird server.
    """

    @classmethod
    def setUpClass(cls):
        cls.url = get_constant("MAGPIE_TEST_REMOTE_SERVER_URL")
        cls.version = utils.TestSetup.get_Version(cls)
        # note: admin credentials to setup data on test instance as needed, but not to be used for these tests
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.setup_admin()
        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-no-auth_ui-user-remote",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-no-auth_ui-group-remote",
                                           raise_missing=False, raise_not_set=False)
        cls.test_service_type = ServiceWPS.service_type
        cls.test_service_name = "magpie-unittest-service-wps"


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_REMOTE
class TestCase_MagpieUI_UsersAuth_Remote(ti.Interface_MagpieUI_UsersAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that require logged AuthN/AuthZ, but lower than ``MAGPIE_ADMIN_GROUP``.

    Use an already running remote bird server.
    """

    @classmethod
    def setUpClass(cls):
        cls.url = get_constant("MAGPIE_TEST_REMOTE_SERVER_URL")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.setup_admin()
        cls.check_requirements()
        cls.version = utils.TestSetup.get_Version(cls)
        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-user-auth_ui-user-remote",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-user-auth_ui-group-remote",
                                           raise_missing=False, raise_not_set=False)


@runner.MAGPIE_TEST_UI
@runner.MAGPIE_TEST_REMOTE
class TestCase_MagpieUI_AdminAuth_Remote(ti.Interface_MagpieUI_AdminAuth, unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test any operation that require at least ``MAGPIE_ADMIN_GROUP`` AuthN/AuthZ.

    Use an already running remote bird server.
    """

    @classmethod
    def setUpClass(cls):
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME", raise_missing=False, raise_not_set=False)
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD", raise_missing=False, raise_not_set=False)
        cls.url = get_constant("MAGPIE_TEST_REMOTE_SERVER_URL")
        cls.headers, cls.cookies = utils.check_or_try_login_user(cls.url, cls.usr, cls.pwd)
        cls.require = "cannot run tests without logged in '{}' user".format(get_constant("MAGPIE_ADMIN_GROUP"))
        cls.setup_admin()
        cls.check_requirements()
        cls.version = utils.TestSetup.get_Version(cls)
        cls.test_user_name = get_constant("MAGPIE_TEST_USER", default_value="unittest-admin-auth_ui-user-remote",
                                          raise_missing=False, raise_not_set=False)
        cls.test_group_name = get_constant("MAGPIE_TEST_GROUP", default_value="unittest-admin-auth_ui-group-remote",
                                           raise_missing=False, raise_not_set=False)
        cls.test_service_type = ServiceAPI.service_type
        cls.test_service_name = "magpie-unittest-ui-admin-remote-service"
