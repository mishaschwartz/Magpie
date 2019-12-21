import json
from sys import exc_info
from typing import TYPE_CHECKING

import six
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPError,
    HTTPException,
    HTTPInternalServerError,
    HTTPOk,
    HTTPRedirection,
    HTTPSuccessful
)

from magpie.utils import (
    CONTENT_TYPE_ANY,
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_PLAIN,
    SUPPORTED_CONTENT_TYPES,
    isclass,
    islambda
)

if TYPE_CHECKING:
    from magpie.typedefs import (  # noqa: F401
        Any, Str, Callable, List, Iterable, Optional, Tuple, Union, JSON, ParamsType, PyramidResponse
    )

# control variables to avoid infinite recursion in case of
# major programming error to avoid application hanging
RAISE_RECURSIVE_SAFEGUARD_MAX = 5
RAISE_RECURSIVE_SAFEGUARD_COUNT = 0


def verify_param(  # noqa: E126
                 # --- verification values ---
                 param,                             # type: Any
                 param_compare=None,                # type: Optional[Union[Any, List[Any]]]
                 # --- output options on failure ---
                 param_name=None,                   # type: Optional[Str]
                 with_param=True,                   # type: bool
                 http_error=HTTPBadRequest,         # type: HTTPError
                 http_kwargs=None,                  # type: Optional[ParamsType]
                 msg_on_fail="",                    # type: Str
                 content=None,                      # type: Optional[JSON]
                 content_type=CONTENT_TYPE_JSON,    # type: Str
                 # --- verification flags (method) ---
                 not_none=False,                    # type: bool
                 not_empty=False,                   # type: bool
                 not_in=False,                      # type: bool
                 not_equal=False,                   # type: bool
                 is_true=False,                     # type: bool
                 is_false=False,                    # type: bool
                 is_none=False,                     # type: bool
                 is_empty=False,                    # type: bool
                 is_in=False,                       # type: bool
                 is_equal=False,                    # type: bool
                 is_type=False,                     # type: bool
                ):                                  # type: (...) -> None
    # pylint: disable=R0912,R0914
    """
    Evaluate various parameter combinations given the requested verification flags. Given a failing verification,
    directly raises the specified ``http_error``. Invalid usage exceptions generated by this verification process are
    treated as :class:`HTTPInternalServerError`. Exceptions are generated using the standard output method.

    :param param: parameter value to evaluate
    :param param_compare:
        other value(s) to test `param` against, can be an iterable (single value resolved as iterable unless `None`)
        to test for `None` type, use `is_none`/`not_none` flags instead
    :param param_name: name of the tested parameter returned in response if specified for debugging purposes
    :param http_error: derived exception to raise on test failure (default: `HTTPBadRequest`)
    :param http_kwargs: additional keyword arguments to pass to `http_error` if called in case of HTTP exception
    :param msg_on_fail: message details to return in HTTP exception if flag condition failed
    :param content: json formatted additional content to provide in case of exception
    :param content_type: format in which to return the exception (one of `magpie.common.SUPPORTED_CONTENT_TYPES`)
    :param not_none: test that `param` is None type
    :param not_empty: test that `param` is an empty string
    :param not_in: test that `param` does not exist in `param_compare` values
    :param not_equal: test that `param` is not equal to `param_compare` value
    :param is_true: test that `param` is `True`
    :param is_false: test that `param` is `False`
    :param is_none: test that `param` is None type
    :param is_empty: test `param` for an empty string
    :param is_in: test that `param` exists in `param_compare` values
    :param is_equal: test that `param` equals `param_compare` value
    :param is_type: test that `param` is of same type as specified by `param_compare` type
    :param with_param: on raise, adds values of `param`, `param_name` and `param_compare` to json response if specified
    :raises `HTTPError`: if tests fail, specified exception is raised (default: `HTTPBadRequest`)
    :raises `HTTPInternalServerError`: for evaluation error
    :return: nothing if all tests passed
    """
    content = {} if content is None else content

    # precondition evaluation of input parameters
    try:
        if not isinstance(not_none, bool):
            raise TypeError("'not_none' is not a 'bool'")
        if not isinstance(not_empty, bool):
            raise TypeError("'not_empty' is not a 'bool'")
        if not isinstance(not_in, bool):
            raise TypeError("'not_in' is not a 'bool'")
        if not isinstance(not_equal, bool):
            raise TypeError("'not_equal' is not a 'bool'")
        if not isinstance(is_true, bool):
            raise TypeError("'is_true' is not a 'bool'")
        if not isinstance(is_false, bool):
            raise TypeError("'is_false' is not a 'bool'")
        if not isinstance(is_none, bool):
            raise TypeError("'is_none' is not a 'bool'")
        if not isinstance(is_empty, bool):
            raise TypeError("'is_empty' is not a 'bool'")
        if not isinstance(is_in, bool):
            raise TypeError("'is_in' is not a 'bool'")
        if not isinstance(is_equal, bool):
            raise TypeError("'is_equal' is not a 'bool'")
        if not isinstance(is_type, bool):
            raise TypeError("'is_type' is not a 'bool'")
        if param_compare is None and (is_in or not_in or is_equal or not_equal):
            raise TypeError("'param_compare' cannot be 'None' with specified test flags")
        if is_equal or not_equal:
            # allow 'different' string literals for comparison, otherwise types must match exactly
            if (not (isinstance(param, six.string_types) and isinstance(param_compare, six.string_types))
                     and type(param) != type(param_compare)):   # noqa: E127 # pylint: disable=C0123
                raise TypeError("'param_compare' cannot be of incompatible type with specified test flags")
        if not hasattr(param_compare, "__iter__") and (is_in or not_in):
            param_compare = [param_compare]
        # error if none of the flags specified
        if not any([not_none, not_empty, not_in, not_equal,
                    is_none, is_empty, is_in, is_equal, is_true, is_false, is_type]):
            raise ValueError("no comparison flag specified for verification")
    except Exception as exc:
        content[u"traceback"] = repr(exc_info())
        content[u"exception"] = repr(exc)
        raise_http(http_error=HTTPInternalServerError, http_kwargs=http_kwargs,
                   content=content, content_type=content_type,
                   detail="Error occurred during parameter verification")

    # evaluate requested parameter combinations
    fail_verify = False
    if not_none:
        fail_verify = fail_verify or (param is None)
    if is_none:
        fail_verify = fail_verify or (param is not None)
    if is_true:
        fail_verify = fail_verify or (param is False)
    if is_false:
        fail_verify = fail_verify or (param is True)
    if not_empty:
        fail_verify = fail_verify or (param == "")
    if is_empty:
        fail_verify = fail_verify or (param != "")
    if not_in:
        fail_verify = fail_verify or (param in param_compare)
    if is_in:
        fail_verify = fail_verify or (param not in param_compare)
    if not_equal:
        fail_verify = fail_verify or (param == param_compare)
    if is_equal:
        fail_verify = fail_verify or (param != param_compare)
    if is_type:
        fail_verify = fail_verify or (not isinstance(param, param_compare))
    if fail_verify:
        if with_param:
            content[u"param"] = {u"value": str(param)}
            if param_name is not None:
                content[u"param"][u"name"] = str(param_name)
            if param_compare is not None:
                content[u"param"][u"compare"] = str(param_compare)
        raise_http(http_error, http_kwargs=http_kwargs, detail=msg_on_fail, content=content, content_type=content_type)


def evaluate_call(call,                                 # type: Callable[[], Any]
                  fallback=None,                        # type: Optional[Callable[[], None]]
                  http_error=HTTPInternalServerError,   # type: HTTPError
                  http_kwargs=None,                     # type: Optional[ParamsType]
                  msg_on_fail="",                       # type: Str
                  content=None,                         # type: Optional[JSON]
                  content_type=CONTENT_TYPE_JSON        # type: Str
                  ):                                    # type: (...) -> Any
    """
    Evaluates the specified ``call`` with a wrapped HTTP exception handling. On failure, tries to call ``fallback`` if
    specified, and finally raises the specified ``http_error``. Any potential error generated by ``fallback`` or
    ``http_error`` themselves are treated as.

    :class:`HTTPInternalServerError`.
    Exceptions are generated using the standard output method formatted based on the specified ``content_type``.

    Example:
        normal call::

            try:
                res = func(args)
            except Exception as exc:
                fb_func()
                raise HTTPExcept(exc.message)

        wrapped call::

            res = evaluate_call(lambda: func(args), fallback=lambda: fb_func(), http_error=HTTPExcept, **kwargs)


    :param call: function to call, *MUST* be specified as `lambda: <function_call>`
    :param fallback: function to call (if any) when `call` failed, *MUST* be `lambda: <function_call>`
    :param http_error: alternative exception to raise on `call` failure
    :param http_kwargs: additional keyword arguments to pass to `http_error` if called in case of HTTP exception
    :param msg_on_fail: message details to return in HTTP exception if `call` failed
    :param content: json formatted additional content to provide in case of exception
    :param content_type: format in which to return the exception (one of `magpie.common.SUPPORTED_CONTENT_TYPES`)
    :raises http_error: on `call` failure
    :raises `HTTPInternalServerError`: on `fallback` failure
    :return: whichever return value `call` might have if no exception occurred
    """
    msg_on_fail = repr(msg_on_fail) if isinstance(msg_on_fail, six.string_types) else msg_on_fail
    if not islambda(call):
        raise_http(http_error=HTTPInternalServerError, http_kwargs=http_kwargs,
                   detail="Input 'call' is not a lambda expression.",
                   content={u"call": {u"detail": msg_on_fail, u"content": repr(content)}},
                   content_type=content_type)

    # preemptively check fallback to avoid possible call exception without valid recovery
    if fallback is not None:
        if not islambda(fallback):
            raise_http(http_error=HTTPInternalServerError, http_kwargs=http_kwargs,
                       detail="Input 'fallback'  is not a lambda expression, not attempting 'call'.",
                       content={u"call": {u"detail": msg_on_fail, u"content": repr(content)}},
                       content_type=content_type)
    try:
        return call()
    except Exception as exc:
        exc_call = repr(exc)
    try:
        if fallback is not None:
            fallback()
    except Exception as exc:
        raise_http(http_error=HTTPInternalServerError, http_kwargs=http_kwargs,
                   detail="Exception occurred during 'fallback' called after failing 'call' exception.",
                   content={u"call": {u"exception": exc_call, u"detail": msg_on_fail, u"content": repr(content)},
                            u"fallback": {u"exception": repr(exc)}},
                   content_type=content_type)
    raise_http(http_error, detail=msg_on_fail, http_kwargs=http_kwargs,
               content={u"call": {u"exception": exc_call, u"content": repr(content)}},
               content_type=content_type)


def valid_http(http_success=HTTPOk,             # type: Optional[HTTPSuccessful]
               http_kwargs=None,                # type: Optional[ParamsType]
               detail="",                       # type: Optional[Str]
               content=None,                    # type: Optional[JSON]
               content_type=CONTENT_TYPE_JSON,  # type: Optional[Str]
               ):                               # type: (...) -> HTTPException
    """
    Returns successful HTTP with standardized information formatted with content type. (see :function:`raise_http` for
    HTTP error calls)

    :param http_success: any derived class from base `HTTPSuccessful` (default: `HTTPOk`)
    :param http_kwargs: additional keyword arguments to pass to `http_success` when called
    :param detail: additional message information (default: empty)
    :param content: json formatted content to include
    :param content_type: format in which to return the exception (one of `magpie.common.SUPPORTED_CONTENT_TYPES`)
    :return `HTTPSuccessful`: formatted successful with additional details and HTTP code
    """
    global RAISE_RECURSIVE_SAFEGUARD_COUNT  # pylint: disable=W0603

    content = dict() if content is None else content
    detail = repr(detail) if not isinstance(detail, six.string_types) else detail
    content_type = CONTENT_TYPE_JSON if content_type == CONTENT_TYPE_ANY else content_type
    http_code, detail, content = validate_params(http_success, [HTTPSuccessful, HTTPRedirection],
                                                 detail, content, content_type)
    json_body = format_content_json_str(http_code, detail, content, content_type)
    resp = generate_response_http_format(http_success, http_kwargs, json_body, output_type=content_type)
    RAISE_RECURSIVE_SAFEGUARD_COUNT = 0  # reset counter for future calls (don't accumulate for different requests)
    return resp


def raise_http(http_error=HTTPInternalServerError,  # type: HTTPError
               http_kwargs=None,                    # type: Optional[ParamsType]
               detail="",                           # type: Str
               content=None,                        # type: Optional[JSON]
               content_type=CONTENT_TYPE_JSON,      # type: Str
               nothrow=False                        # type: bool
               ):                                   # type: (...) -> Optional[HTTPException]
    """
    Raises error HTTP with standardized information formatted with content type.

    The content contains the corresponding http error code, the provided message as detail and
    optional specified additional json content (kwarg dict).

    .. seealso::
        :func:`valid_http` for HTTP successful calls

    :param http_error: any derived class from base `HTTPError` (default: `HTTPInternalServerError`)
    :param http_kwargs: additional keyword arguments to pass to `http_error` if called in case of HTTP exception
    :param detail: additional message information (default: empty)
    :param content: json formatted content to include
    :param content_type: format in which to return the exception (one of `magpie.common.SUPPORTED_CONTENT_TYPES`)
    :param nothrow: returns the error response instead of raising it automatically, but still handles execution errors
    :raises HTTPError: formatted raised exception with additional details and HTTP code
    :returns: HTTPError formatted exception with additional details and HTTP code only if `nothrow` is `True`
    """

    # fail-fast if recursion generates too many calls
    # this would happen only if a major programming error occurred within this function
    global RAISE_RECURSIVE_SAFEGUARD_MAX    # pylint: disable=W0603
    global RAISE_RECURSIVE_SAFEGUARD_COUNT  # pylint: disable=W0603
    RAISE_RECURSIVE_SAFEGUARD_COUNT = RAISE_RECURSIVE_SAFEGUARD_COUNT + 1
    if RAISE_RECURSIVE_SAFEGUARD_COUNT > RAISE_RECURSIVE_SAFEGUARD_MAX:
        raise HTTPInternalServerError(detail="Terminated. Too many recursions of `raise_http`")

    # try dumping content with json format, `HTTPInternalServerError` with caller info if fails.
    # content is added manually to avoid auto-format and suppression of fields by `HTTPException`
    content_type = CONTENT_TYPE_JSON if content_type == CONTENT_TYPE_ANY else content_type
    _, detail, content = validate_params(http_error, HTTPError, detail, content, content_type)
    json_body = format_content_json_str(http_error.code, detail, content, content_type)
    resp = generate_response_http_format(http_error, http_kwargs, json_body, output_type=content_type)

    # reset counter for future calls (don't accumulate for different requests)
    # following raise is the last in the chain since it wasn't triggered by other functions
    RAISE_RECURSIVE_SAFEGUARD_COUNT = 0
    if nothrow:
        return resp
    raise resp


def validate_params(http_class,     # type: HTTPException
                    http_base,      # type: Union[HTTPException, Iterable[HTTPException]]
                    detail,         # type: Str
                    content,        # type: Optional[JSON]
                    content_type,   # type: Str
                    ):              # type: (...) -> Tuple[int, Str, JSON]
    """
    Validates parameter types and formats required by :function:`valid_http` and :function:`raise_http`.

    :param http_class: any derived class from base `HTTPException` to verify
    :param http_base: any derived sub-class(es) from base `HTTPException` as minimum requirement for `http_class`
        (ie: 2xx, 4xx, 5xx codes). Can be a single class of an iterable of possible requirements (any).
    :param detail: additional message information (default: empty)
    :param content: json formatted content to include
    :param content_type: format in which to return the exception (one of `magpie.common.SUPPORTED_CONTENT_TYPES`)
    :raise `HTTPInternalServerError`: if any parameter is of invalid expected format
    :returns http_code, detail, content: parameters with corrected and validated format if applicable
    """
    # verify input arguments, raise `HTTPInternalServerError` with caller info if invalid
    # cannot be done within a try/except because it would always trigger with `raise_http`
    content = dict() if content is None else content
    detail = repr(detail) if not isinstance(detail, six.string_types) else detail
    caller = {u"content": content, u"type": content_type, u"detail": detail, u"code": 520}  # "unknown" code error
    verify_param(isclass(http_class), param_name="http_class", is_true=True,
                 http_error=HTTPInternalServerError, content_type=CONTENT_TYPE_JSON, content={u"caller": caller},
                 msg_on_fail="Object specified is not a class, class derived from `HTTPException` is expected.")
    # if `http_class` derives from `http_base` (ex: `HTTPSuccessful` or `HTTPError`) it is of proper requested type
    # if it derives from `HTTPException`, it *could* be different than base (ex: 2xx instead of 4xx codes)
    # return 'unknown error' (520) if not of lowest level base `HTTPException`, otherwise use the available code
    http_base = tuple(http_base if hasattr(http_base, "__iter__") else [http_base])
    # noinspection PyUnresolvedReferences
    http_code = http_class.code if issubclass(http_class, http_base) else \
               http_class.code if issubclass(http_class, HTTPException) else 520  # noqa: F401
    caller[u"code"] = http_code
    verify_param(issubclass(http_class, http_base), param_name="http_base", is_true=True,
                 http_error=HTTPInternalServerError, content_type=CONTENT_TYPE_JSON, content={u"caller": caller},
                 msg_on_fail="Invalid 'http_base' derived class specified.")
    verify_param(content_type, param_name="content_type", param_compare=SUPPORTED_CONTENT_TYPES, is_in=True,
                 http_error=HTTPInternalServerError, content_type=CONTENT_TYPE_JSON, content={u"caller": caller},
                 msg_on_fail="Invalid 'content_type' specified for exception output.")
    return http_code, detail, content


def format_content_json_str(http_code, detail, content, content_type):
    """
    Inserts the code, details, content and type within the body using json format. Includes also any other specified
    json formatted content in the body. Returns the whole json body as a single string for output.

    :raise `HTTPInternalServerError`: if parsing of the json content failed
    :returns: formatted json content as string with added HTTP code and details
    """
    json_body = {}
    try:
        content[u"code"] = http_code
        content[u"detail"] = detail
        content[u"type"] = content_type
        json_body = json.dumps(content)
    except Exception as exc:    # pylint: disable=W0703
        msg = "Dumping json content '{!s}' resulted in exception '{!r}'.".format(content, exc)
        raise_http(http_error=HTTPInternalServerError, detail=msg,
                   content_type=CONTENT_TYPE_JSON,
                   content={u"traceback": repr(exc_info()),
                            u"exception": repr(exc),
                            u"caller": {u"content": repr(content),  # raw string to avoid recursive json.dumps error
                                        u"detail": detail,
                                        u"code": http_code,
                                        u"type": content_type}})
    return json_body


def generate_response_http_format(http_class, http_kwargs, json_content, output_type=CONTENT_TYPE_PLAIN):
    # type: (Union[HTTPException, PyramidResponse], ParamsType, JSON, Optional[Str]) -> PyramidResponse
    """
    Formats the HTTP response output according to desired ``output_type`` using provided HTTP code and content.

    :param http_class: `HTTPException` derived class to use for output (code, generic title/explanation, etc.)
    :param http_kwargs: additional keyword arguments to pass to `http_class` when called
    :param json_content: formatted json content providing additional details for the response cause
    :param output_type: one of `magpie.common.SUPPORTED_CONTENT_TYPES` (default: `magpie.common.CONTENT_TYPE_PLAIN`)
    :return: `http_class` instance with requested information and output type if creation succeeds
    :raises: `HTTPInternalServerError` instance details about requested information and output type if creation fails
    """
    # content body is added manually to avoid auto-format and suppression of fields by `HTTPException`
    json_content = str(json_content) if not isinstance(json_content, six.string_types) else json_content

    # adjust additional keyword arguments and try building the http response class with them
    http_kwargs = dict() if http_kwargs is None else http_kwargs
    try:
        # directly output json
        if output_type == CONTENT_TYPE_JSON:
            json_type = "{}; charset=UTF-8".format(CONTENT_TYPE_JSON)
            http_response = http_class(body=json_content, content_type=json_type, **http_kwargs)

        # otherwise json is contained within the html <body> section
        elif output_type == CONTENT_TYPE_HTML:
            # add preformat <pre> section to output as is within the <body> section
            html_body = "{}<br><h2>Exception Details</h2>" \
                        "<pre style='word-wrap: break-word; white-space: pre-wrap;'>{}</pre>" \
                .format(http_class.explanation, json_content)
            http_response = http_class(body_template=html_body, content_type=CONTENT_TYPE_HTML, **http_kwargs)

        # default back to plain text
        else:
            http_response = http_class(body=json_content, content_type=CONTENT_TYPE_PLAIN, **http_kwargs)

        return http_response
    except Exception as exc:  # pylint: disable=W0703
        raise_http(http_error=HTTPInternalServerError, detail="Failed to build HTTP response",
                   content={u"traceback": repr(exc_info()), u"exception": repr(exc),
                            u"caller": {u"http_kwargs": repr(http_kwargs),
                                        u"http_class": repr(http_class),
                                        u"output_type": str(output_type)}})
