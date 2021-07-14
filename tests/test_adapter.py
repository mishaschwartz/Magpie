import random
import unittest
from typing import TYPE_CHECKING

import pytest
import six
from pyramid.httpexceptions import HTTPNotFound

from magpie import __meta__
from magpie.constants import get_constant
from magpie.permissions import Permission
from magpie.services import ServiceAPI, ServiceInterface, ServiceWPS, invalidate_service
from tests import interfaces as ti
from tests import runner, utils

if six.PY3:
    from magpie.adapter.magpieowssecurity import MagpieOWSSecurity, OWSAccessForbidden

if TYPE_CHECKING:
    from typing import Callable, Tuple
    from mock import MagicMock


@unittest.skipIf(six.PY2, "Unsupported Twitcher for MagpieAdapter in Python 2")
@pytest.mark.skipif(six.PY2, reason="Unsupported Twitcher for MagpieAdapter in Python 2")
@runner.MAGPIE_TEST_LOCAL
@runner.MAGPIE_TEST_ADAPTER
@runner.MAGPIE_TEST_FUNCTIONAL
class TestAdapter(ti.SetupMagpieAdapter, ti.UserTestCase, ti.BaseTestCase):
    """
    Validation of general :class:`magpie.adapter.MagpieAdapter` operations and its underlying service/security handling.
    """

    __test__ = True

    @classmethod
    @utils.mocked_get_settings
    def setUpClass(cls):
        cls.version = __meta__.__version__
        cls.app = utils.get_test_magpie_app()
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME")
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD")
        cls.settings = utils.get_app_or_url(cls).app.registry.settings

        # following will be wiped on setup
        cls.test_user_name = "unittest-adapter-user"
        cls.test_group_name = "unittest-adapter-group"
        cls.test_service_name = "unittest-adapter-service"
        cls.test_service_type = ServiceAPI.service_type
        cls.test_resource_name = "test"
        cls.test_resource_type = "route"

        cls.setup_adapter()
        cls.setup_admin()
        cls.login_admin()

    def setUp(self):
        ti.UserTestCase.setUp(self)
        info = utils.TestSetup.create_TestService(self)
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="read")
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="write")
        info = utils.TestSetup.create_TestServiceResource(self)
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="read")
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="write")
        self.login_test_user()

    @utils.mocked_get_settings
    def test_unauthenticated_service_blocked(self):
        """
        Validate missing authentication token blocks access to the service if not publicly accessible.
        """
        utils.check_or_try_logout_user(self)
        self.test_headers = None
        self.test_cookies = None

        path = "/ows/proxy/{}".format(self.test_service_name)
        req = self.mock_request(path, method="GET")
        utils.check_raises(lambda: self.ows.check_request(req), OWSAccessForbidden, msg="Using [GET, {}]".format(path))
        req = self.mock_request(path, method="POST")
        utils.check_raises(lambda: self.ows.check_request(req), OWSAccessForbidden, msg="Using [POST, {}]".format(path))

    @utils.mocked_get_settings
    def test_unauthenticated_resource_allowed(self):
        """
        Validate granted access to a resource specified as publicly accessible even without any authentication token.
        """
        utils.check_or_try_logout_user(self)
        self.test_headers = None
        self.test_cookies = None

        path = "/ows/proxy/{}/{}".format(self.test_service_name, self.test_resource_name)
        req = self.mock_request(path, method="GET")
        utils.check_raises(lambda: self.ows.check_request(req), OWSAccessForbidden, msg="Using [GET, {}]".format(path))
        req = self.mock_request(path, method="POST")
        utils.check_raises(lambda: self.ows.check_request(req), OWSAccessForbidden, msg="Using [POST, {}]".format(path))

    @utils.mocked_get_settings
    def test_unknown_service(self):
        """
        Validate that unknown service-name is handled correctly.
        """
        self.login_test_user()

        # validate it works correctly for known service
        path = "/ows/proxy/{}".format(self.test_service_name)
        req = self.mock_request(path, method="GET")
        utils.check_no_raise(lambda: self.ows.check_request(req), msg="Using [GET, {}]".format(path))

        # when service is unknown, Magpie cannot resolve it and directly raises not found
        path = "/ows/proxy/unittest-unknown-service"
        req = self.mock_request(path, method="GET")
        utils.check_raises(lambda: self.ows.check_request(req), HTTPNotFound, msg="Using [GET, {}]".format(path))

    @utils.mocked_get_settings
    def test_unknown_resource_under_service(self):
        """
        Evaluate use-case where requested resource when parsing the request corresponds to non-existing element.

        If the targeted resource does not exist in database, `Magpie` should still allow access if its closest
        available parent permission results into Allow/Recursive.

        If the closest parent permission permission is either Match-scoped or explicit Deny, access should be refused.
        """
        self.login_test_user()

        # validate it works correctly for known Magpie resource
        path = "/ows/proxy/{}/{}".format(self.test_service_name, self.test_resource_name)
        req = self.mock_request(path, method="GET")
        utils.check_no_raise(lambda: self.ows.check_request(req), msg="Using [GET, {}]".format(path))

        # resource is unknown, but user permission grants access to whatever 'resource' is supposedly located there
        # up to underlying service to return whichever status is appropriate, but request is forwarded as considered
        # resolved for Magpie/Twitcher roles
        path = "/ows/proxy/{}/{}".format(self.test_service_name, "unittest-unknown-resource")
        req = self.mock_request(path, method="GET")
        utils.check_no_raise(lambda: self.ows.check_request(req), msg="Using [GET, {}]".format(path))


@runner.MAGPIE_TEST_LOCAL
@runner.MAGPIE_TEST_ADAPTER
@runner.MAGPIE_TEST_FUNCTIONAL
class TestAdapterCaching(ti.SetupMagpieAdapter, ti.UserTestCase, ti.BaseTestCase):
    """
    Base methods for testing requests parsing and :term:`ACL` resolution when caching is enabled.

    .. warning::
        Caching tests are time-dependant.
        While debugging, exceeding the value of :data:`cache_expire` could make a test fail because cache was reset.
        This is the case especially for requests count comparisons.

    .. seealso::
        - :class:`TestAdapterCachingAllRegions`
        - :class:`TestAdapterCachingPartialRegions`
    """
    # pylint: disable=C0103,invalid-name
    __test__ = False
    test_headers = None
    test_cookies = None
    cache_expire = None
    cache_enabled = False
    cache_settings = None  # if defined, overrides other 'cache_<>' parameters above (explicit 'beaker' configuration)
    cache_reset_headers = {"Cache-Control": "no-cache"}  # requests with this header reset caches to force function call

    @classmethod
    def setUpClass(cls):
        cls.version = __meta__.__version__
        cls.settings = {}
        cls.app = None
        cls.grp = get_constant("MAGPIE_ADMIN_GROUP")
        cls.usr = get_constant("MAGPIE_TEST_ADMIN_USERNAME")
        cls.pwd = get_constant("MAGPIE_TEST_ADMIN_PASSWORD")

        # following will be wiped on setup
        cls.test_user_name = "unittest-adapter-cache-user"
        cls.test_group_name = "unittest-adapter-cache-group"
        cls.test_service_name = "unittest-adapter-service"
        cls.test_service_type = ServiceAPI.service_type
        cls.test_resource_type = "route"

    @utils.mocked_get_settings
    def setUp(self):
        self.reset_cached_app(settings=self.cache_settings)
        ti.UserTestCase.setUp(self)
        self.cookies = None
        self.headers, self.cookies = utils.check_or_try_login_user(self, self.usr, self.pwd, use_ui_form_submit=True)
        self.require = "cannot run tests without logged in user with '{}' permissions".format(self.grp)
        self.login_admin()
        utils.TestSetup.delete_TestService(self)
        utils.TestSetup.create_TestService(self)
        invalidate_service(self.test_service_name)

    @classmethod
    def reset_cached_app(cls, settings=None):
        cache_settings = cls.settings.copy()
        if not settings:
            utils.setup_cache_settings(cache_settings, force=True, enabled=cls.cache_enabled, expire=cls.cache_expire)
        else:
            cache_settings.update(settings)

        cls.app = utils.get_test_magpie_app(settings=cache_settings)
        cls.setup_adapter(setup_cache=False)  # don't override adapter cache settings pre-defined above
        cls.setup_admin()

    def run_with_caching_mocks(self, service, operations):
        # type: (ServiceInterface, Callable[[], None]) -> Tuple[MagicMock, MagicMock, MagicMock, MagicMock]
        """
        Runs the operations with mocks wrapping important functions that allow counting cached vs non-cached calls.

        :param service: handle to service that will be called/cached and retrieved during requests
        :param operations: callable that should trigger the requests/caching tests (no argument, no return)
        :returns
            Tuple of mock handles to called operations:
            - service calls retrieved from cache
            - service calls generated from request
            - ACL resolution retrieved from cache
            - ACL resolution computed from request
        """
        def mocked_service_factory(__test_service, test_request):
            service.request = test_request
            return service

        # WARNING:
        #  In both cases below, we cannot mock the cached method directly since beaker needs it to do caching retrieval.
        #  Instead, mock a function before each cached method and another within cached method to compare call-counts.

        # wrap 'get_service' which calls the cached method '_get_service_cached', which in turn calls 'service_factory'
        # when caching takes effect, 'service_factory' does not get called as the cached service is returned directly
        with utils.wrapped_call(MagpieOWSSecurity, "get_service", self.ows) as mock_service_cached:
            with utils.wrapped_call("magpie.adapter.magpieowssecurity.service_factory",
                                    side_effect=mocked_service_factory) as mock_service_factory:
                # wrap '__acl__' which calls '_get_acl_cached', that in turns calls '_get_acl' when resolving real ACL
                with utils.wrapped_call(ServiceInterface, "__acl__", service) as mock_acl_cached:
                    with utils.wrapped_call(ServiceInterface, "_get_acl", service) as mock_acl_resolve:
                        operations()
        return mock_service_cached, mock_service_factory, mock_acl_cached, mock_acl_resolve


class TestAdapterCachingAllRegions(TestAdapterCaching):
    __test__ = True
    test_headers = None
    test_cookies = None
    cache_expire = 600
    cache_enabled = True
    cache_reset_headers = {"Cache-Control": "no-cache"}

    @utils.mocked_get_settings
    def test_access_cached_service(self):
        """
        Verify caching operation of adapter to retrieve the requested service.

        Caching limits retrieval of service implementation from database service definition matched by service name.
        """
        number_calls = 10
        admin_headers = self.headers.copy()
        admin_cookies = self.cookies.copy()
        admin_no_cache = self.cache_reset_headers.copy()
        admin_no_cache.update(admin_headers)

        # wrap 'get_service' which calls the cached method, which in turn calls 'service_factory'
        # when caching takes effect, 'service_factory' does not get called as the cached service is returned directly
        with utils.wrapped_call(MagpieOWSSecurity, "get_service", self.ows) as mock_cached:
            with utils.wrapped_call("magpie.adapter.magpieowssecurity.service_factory") as mock_service:

                # initial request to ensure functions get cached once from scratch
                path = "/ows/proxy/{}".format(self.test_service_name)
                msg = "Using [GET, {}]".format(path)
                req = self.mock_request(path, method="GET", headers=admin_no_cache, cookies=admin_cookies)
                utils.check_no_raise(lambda: self.ows.check_request(req), msg=msg)

                # run many requests which should directly return the previously cached result
                req = self.mock_request(path, method="GET", headers=admin_headers, cookies=admin_cookies)
                for _ in range(number_calls):
                    utils.check_no_raise(lambda: self.ows.check_request(req), msg=msg)

        utils.check_val_equal(mock_service.call_count, 1, msg="Real call expected only on first run before caching")
        utils.check_val_equal(mock_cached.call_count, number_calls + 1, msg="Cached call expected for each request")

    @utils.mocked_get_settings
    def test_access_cached_service_by_other_user(self):
        """
        Verify that cached service doesn't result into invalid permission access when different user sends the request.

        Although service is cached, the resolution of the given user doing the request must still resolve correctly.
        """

        admin_headers = self.headers.copy()
        admin_cookies = self.cookies.copy()
        admin_no_cache = self.cache_reset_headers.copy()
        admin_no_cache.update(admin_headers)

        # wrap 'get_service' which calls the cached method, which in turn calls 'service_factory'
        # when caching takes effect, 'service_factory' does not get called as the cached service is returned directly
        with utils.wrapped_call(MagpieOWSSecurity, "get_service", self.ows) as wrapped_service:
            with utils.wrapped_call("magpie.adapter.magpieowssecurity.service_factory") as wrapped_cached:

                # always hit the same endpoint for each request
                path = "/ows/proxy/{}".format(self.test_service_name)
                msg = "Using [GET, {}]".format(path)

                # initial request to ensure functions get cached once from scratch
                req = self.mock_request(path, method="GET", headers=admin_no_cache, cookies=admin_cookies)
                utils.check_no_raise(lambda: self.ows.check_request(req), msg=msg)

                # same request by admin, but with caching from previous call allowed for sanity check
                req = self.mock_request(path, method="GET", headers=self.headers, cookies=self.cookies)
                utils.check_no_raise(lambda: self.ows.check_request(req), msg=msg)

                # finally, request for unauthorized user access to the service with cache still enabled
                self.login_test_user()
                req = self.mock_request(path, method="GET")
                msg += " Expected unauthorized user refused access, not inheriting access of previous cached request"
                utils.check_raises(lambda: self.ows.check_request(req), OWSAccessForbidden, msg=msg)

        utils.check_val_equal(wrapped_cached.call_count, 1, msg="Real call expected only on first run before caching")
        utils.check_val_equal(wrapped_service.call_count, 3, msg="Service call expected for each request")

    @utils.mocked_get_settings
    def test_retrieve_cached_acl(self):
        """
        Validate caching of :term:`ACL` resolution against repeated combinations of caching arguments.

        Caching method takes as inputs combinations of (:term:`User`, :term:`Resource`, :term:`Permission`).

        Verify that the caching takes effect, but also that it is properly managed between distinct consecutive
        requests. Multiple combinations of :term:`ACL` resolution requests are sent in random order to ensure they
        don't invalidate other caches (of other combinations), while still producing valid results for the relevant
        :term:`Resource` the :term:`User` attempts to obtain :term:`Permission` access.

        When :term:`ACL` caching is applied properly, the complete computation of the access result should only be
        accomplished on the first call of each combination, and all following ones (within the caching timeout) will
        resolve from the cache.
        """
        # create some test resources under the service with permission for the user
        # service not allowed access, resource allowed
        res1_name = "test1"
        res2_name = "test2"
        res1_path = "/ows/proxy/{}/{}".format(self.test_service_name, res1_name)
        res2_path = "/ows/proxy/{}/{}".format(self.test_service_name, res2_name)
        info = utils.TestSetup.create_TestServiceResource(self, override_resource_name=res1_name)
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="read")
        info = utils.TestSetup.create_TestServiceResource(self, override_resource_name=res2_name)
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info, override_permission="write")

        no_cache_header = self.cache_reset_headers.copy()
        admin_cookies = self.cookies.copy()
        admin_headers = self.headers.copy()
        self.login_test_user()
        user_cookies = self.test_cookies.copy()
        user_headers = self.test_headers.copy()
        utils.check_or_try_logout_user(self)
        self.test_headers = None
        self.test_cookies = None

        test_requests = [
            # allowed because admin
            (True, self.mock_request(res1_path, method="GET", headers=admin_headers, cookies=admin_cookies)),
            (True, self.mock_request(res1_path, method="POST", headers=admin_headers, cookies=admin_cookies)),
            (True, self.mock_request(res2_path, method="GET", headers=admin_headers, cookies=admin_cookies)),
            (True, self.mock_request(res2_path, method="POST", headers=admin_headers, cookies=admin_cookies)),
            # allowed/denied based on (user, resource, permission) combination
            (True, self.mock_request(res1_path, method="GET", headers=user_headers, cookies=user_cookies)),
            (False, self.mock_request(res1_path, method="POST", headers=user_headers, cookies=user_cookies)),
            (False, self.mock_request(res2_path, method="GET", headers=user_headers, cookies=user_cookies)),
            (True, self.mock_request(res2_path, method="POST", headers=user_headers, cookies=user_cookies)),
        ]
        number_duplicate_call_cached = 20
        cache_requests = test_requests * number_duplicate_call_cached
        random.shuffle(cache_requests)

        # each method targets a different Permission, each path a different Resource, and each cookies a different user
        token = get_constant("MAGPIE_COOKIE_NAME")
        unique_calls = set((req.method, req.path_qs, req.cookies[token]) for _, req in test_requests + cache_requests)

        def run_check(test_requests_set, cached):
            _cached = " (cached)" if cached else ""
            for _allowed, _request in test_requests_set:
                _cookie = _request.cookies[token]
                _user = self.test_user_name if _cookie == user_cookies[token] else "admin"
                _msg = "Using [{}, {}]{} with user [{}]".format(_request.method, _request.path_qs, _cached, _user)
                if not cached:
                    _request.headers.update(no_cache_header)
                else:
                    _request.headers.pop("Cache-Control", None)
                if _allowed:
                    utils.check_no_raise(lambda: self.ows.check_request(_request), msg=_msg)
                else:
                    utils.check_raises(lambda: self.ows.check_request(_request), OWSAccessForbidden, msg=_msg)

        # obtain a reference to the 'service' that should be returned by 'service_factory' such that we can
        # prepare wrapped mock references to its '__acl__' and '_get_acl' methods
        tmp_req = test_requests[0][1]
        service = self.ows.get_service(tmp_req)

        def test_ops():
            # run all requests with caching disabled to initialize their expire duration
            run_check(test_requests, False)
            # then, do exactly the same but with caches enabled for requests in random order
            # all caches should remain active for the whole duration and not conflict with each other
            run_check(cache_requests, True)

        mock_service_cached, mock_service, mock_acl_cached, mock_acl = self.run_with_caching_mocks(service, test_ops)

        # there should be as many service resolution as there are requests, but only first ones without cache fetches it
        # for ACL resolution, there should also be as many as there are requests, but actual computation will be limited
        # to the number of combinations without caching, and all others only return the precomputed cache result
        total_cached = len(cache_requests)
        total_no_cache = len(test_requests)
        total_calls = total_cached + total_no_cache
        total_acl_cached = len(unique_calls)
        utils.check_val_equal(mock_service_cached.call_count, total_calls,
                              msg="Cached service call expected for each request")
        utils.check_val_equal(mock_acl_cached.call_count, total_calls,
                              msg="Cached ACL resolution expected for each request")
        utils.check_val_equal(mock_service.call_count, total_no_cache,
                              msg="Real service call expected for each no-cache request, but not for other cached ones")
        utils.check_val_equal(mock_acl.call_count, total_acl_cached,
                              msg="Real ACL call expected only on first unique combination of cached ACL")

    @utils.mocked_get_settings
    def test_cached_service_ows_parser_request(self):
        """
        Validate that OWS parser resolves the correct request reference from previously fetched and cached service.

        Because many objects refer to the :class:`pyramid.request.Request` for different purposes, some object cached
        and others referring to that cached state, updated references must be ensured everywhere for new requests that
        could change request query parameters, headers, authentication tokens, etc.
        """

        anonymous = get_constant("MAGPIE_ANONYMOUS_USER")

        # create some test OWS service (WPS used, but could be any)
        svc_name = self.test_service_name + "_wps"
        svc_type = ServiceWPS.service_type
        utils.TestSetup.delete_TestService(self, override_service_name=svc_name)
        svc_info = utils.TestSetup.create_TestService(self,
                                                      override_service_name=svc_name,
                                                      override_service_type=svc_type)
        utils.TestSetup.create_TestUserResourcePermission(self,
                                                          resource_info=svc_info,
                                                          override_user_name=anonymous,
                                                          override_permission=Permission.GET_CAPABILITIES)
        utils.TestSetup.create_TestUserResourcePermission(self,
                                                          resource_info=svc_info,
                                                          override_user_name=anonymous,
                                                          override_permission=Permission.EXECUTE)

        utils.check_or_try_logout_user(self)  # anonymous
        self.test_headers = None
        self.test_cookies = None

        svc_path_getcap = "/ows/proxy/{}?request=GetCapabilities&service=WPS".format(svc_name)  # allowed
        svc_path_desc = "/ows/proxy/{}?request=DescribeProcess&service=WPS".format(svc_name)  # denied
        svc_path_exec = "/ows/proxy/{}?request=Execute&service=WPS".format(svc_name)  # denied
        test_requests = [
            # First request should trigger caching of the service as 'Allowed' and corresponding ACL resolution.
            (True, self.mock_request(svc_path_getcap, method="GET")),
            # Following requests should reuse the cached service, not triggering another 'service_factory' operation.
            # On the other hand, the distinct query parameter 'request=<>' should trigger a different ACL resolution.
            # Since they all use 'service.request' object inside cached 'service', correct update of references
            # to 'parser.request' should properly resolve as defined access.
            # Test one of each Allowed/Denied resolution, to ensure the cached 'service' did not interfere with ACL
            (False, self.mock_request(svc_path_desc, method="GET")),
            (True, self.mock_request(svc_path_exec, method="GET")),
        ]
        # Run multiple other requests afterwards to ensure that mix-and-match of above combinations still make use
        # of the cached service and cached ACL following first resolution of each case.
        number_duplicate_call_cached = 5
        cache_requests = test_requests * number_duplicate_call_cached
        random.shuffle(cache_requests)

        # each method targets a different Permission (via query param 'request=<>')
        unique_calls = set((req.method, req.path_qs) for _, req in test_requests + cache_requests)

        def run_check(test_requests_set):
            for _allowed, _request in test_requests_set:
                _msg = "Using [{}, {}] with user [{}]".format(_request.method, _request.path_qs, anonymous)
                if _allowed:
                    utils.check_no_raise(lambda: self.ows.check_request(_request), msg=_msg)
                else:
                    utils.check_raises(lambda: self.ows.check_request(_request), OWSAccessForbidden, msg=_msg)

        # obtain a reference to the 'service' that should be returned by 'service_factory' such that we can
        # prepare wrapped mock references to its '__acl__' and '_get_acl' methods
        # ensure following 'get_service' call doesn't trigger caching before running the tests with no-cache header
        tmp_req = self.mock_request(svc_path_getcap, method="GET", headers=self.cache_reset_headers)
        service = self.ows.get_service(tmp_req)
        invalidate_service(svc_name)

        def test_ops():
            run_check(test_requests)  # run all requests that triggers initial caching
            run_check(cache_requests)  # run them using caches, not triggering full ACL resolutions

        mock_service_cached, mock_service, mock_acl_cached, mock_acl = self.run_with_caching_mocks(service, test_ops)

        # There should be as many service resolution as there are requests, but only first one without cache fetches it.
        # ACL resolution should also occur once for each 'request=<>' permission.
        total_cached = len(cache_requests)
        total_no_cache = len(test_requests)
        total_calls = total_cached + total_no_cache
        total_acl_cached = len(unique_calls)
        utils.check_val_equal(mock_service_cached.call_count, total_calls,
                              msg="Cached service call expected for each request")
        utils.check_val_equal(mock_acl_cached.call_count, total_calls,
                              msg="Cached ACL resolution expected for each request")
        utils.check_val_equal(mock_service.call_count, 1,
                              msg="Real service call expected only for first call since it is always the same service")
        utils.check_val_equal(mock_acl.call_count, total_acl_cached,
                              msg="Real ACL expected only once per unique permission combination")


class TestAdapterCachingPartialRegions(TestAdapterCaching):
    __test__ = True
    test_headers = None
    test_cookies = None
    cache_expire = None
    cache_enabled = True
    # below cache settings overrides all cache parameters above
    cache_settings = {"cache.enabled": "false", "cache.acl.enabled": "false", "cache.service.enabled": "true"}
    cache_reset_headers = {"Cache-Control": "no-cache"}

    @utils.mocked_get_settings
    def test_cached_service_uncached_acl(self):
        """
        Validate that service with cached enabled combined with ACL not cached still works as expected.

        When service is correctly retrieved from cache, but ACL employed to resolve effective permissions on that
        service are not yet cached, the database session state must be refreshed and applied to that cached service
        in other to properly resolve resource/permission hierarchy.

        .. seealso::
            :meth:`magpie.services.ServiceInterface.effective_permissions` (around start of loop)
        """
        anonymous = get_constant("MAGPIE_ANONYMOUS_USER")
        svc_name = self.test_service_name + "_wps-partial-cache"
        svc_type = ServiceWPS.service_type
        utils.TestSetup.delete_TestService(self, override_service_name=svc_name)
        info = utils.TestSetup.create_TestService(self, override_service_name=svc_name, override_service_type=svc_type)
        utils.TestSetup.create_TestUserResourcePermission(self, resource_info=info,
                                                          override_user_name=anonymous,
                                                          override_permission=Permission.GET_CAPABILITIES)
        utils.check_or_try_logout_user(self)

        svc_path_getcap = "/ows/proxy/{}?request=GetCapabilities&service=WPS".format(svc_name)  # allowed
        svc_path_desc = "/ows/proxy/{}?request=DescribeProcess&service=WPS".format(svc_name)  # denied
        svc_path_exec = "/ows/proxy/{}?request=Execute&service=WPS".format(svc_name)  # denied
        test_requests = [
            # First request should trigger caching of the service, following use the cache
            # For each case, ACL should never be cached.
            (True, self.mock_request(svc_path_getcap, method="GET")),
            (False, self.mock_request(svc_path_desc, method="GET")),
            (False, self.mock_request(svc_path_exec, method="GET")),
        ]
        # Run multiple other requests afterwards to ensure that mix-and-match of above combinations still make use
        # of the cached service and cached ACL following first resolution of each case.
        number_duplicate_call_cached = 5
        cache_requests = test_requests * number_duplicate_call_cached
        random.shuffle(cache_requests)

        def run_check(test_requests_set):
            for _allowed, _request in test_requests_set:
                _msg = "Using [{}, {}] with user [{}]".format(_request.method, _request.path_qs, anonymous)
                if _allowed:
                    utils.check_no_raise(lambda: self.ows.check_request(_request), msg=_msg)
                else:
                    utils.check_raises(lambda: self.ows.check_request(_request), OWSAccessForbidden, msg=_msg)

        # obtain a reference to the 'service' that should be returned by 'service_factory' such that we can
        # prepare wrapped mock references to its '__acl__' and '_get_acl' methods
        # ensure following 'get_service' call doesn't trigger caching before running the tests with no-cache header
        tmp_req = self.mock_request(svc_path_getcap, method="GET", headers=self.cache_reset_headers)
        service = self.ows.get_service(tmp_req)
        invalidate_service(svc_name)

        def test_ops():
            run_check(test_requests)  # run all requests that triggers initial caching
            run_check(cache_requests)  # run them using caches, not triggering full ACL resolutions

        mock_service_cached, mock_service, mock_acl_cached, mock_acl = self.run_with_caching_mocks(service, test_ops)

        # There should be as many service resolution as there are requests, but only first one without cache fetches it.
        # ACL resolution should also occur once for each 'request=<>' permission.
        total_cached = len(cache_requests)
        total_no_cache = len(test_requests)
        total_calls = total_cached + total_no_cache
        utils.check_val_equal(mock_service_cached.call_count, total_calls,
                              msg="Cached service call expected for each request")
        utils.check_val_equal(mock_acl_cached.call_count, total_calls,
                              msg="Cached ACL resolution expected for each request")
        utils.check_val_equal(mock_service.call_count, 1,
                              msg="Real service call expected only for first call since it is always the same service")
        utils.check_val_equal(mock_acl.call_count, total_calls,
                              msg="Real ACL call expected every time (cache disabled in ACL region setting)")
