from typing import TYPE_CHECKING

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPCreated,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPOk
)
from pyramid.settings import asbool
from ziggurat_foundations.models.services.group import GroupService
from ziggurat_foundations.models.services.group_resource_permission import GroupResourcePermissionService
from ziggurat_foundations.models.services.resource import ResourceService

from magpie import models
from magpie.api import exception as ax
from magpie.api import schemas as s
from magpie.api.management.group.group_formats import format_group
from magpie.api.management.resource.resource_formats import format_resource
from magpie.api.management.resource.resource_utils import check_valid_service_or_resource_permission
from magpie.api.management.service.service_formats import format_service, format_service_resources
from magpie.permissions import PermissionSet, PermissionType, format_permissions
from magpie.services import SERVICE_TYPE_DICT

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Iterable, List, Optional

    from pyramid.httpexceptions import HTTPException
    from sqlalchemy.orm.session import Session

    from magpie.permissions import Permission
    from magpie.typedefs import JSON, ResourcePermissionMap, ServiceOrResourceType, Str


def get_all_group_names(db_session):
    # type: (Session) -> List[Str]
    """
    Get all existing group names from the database.
    """
    group_names = ax.evaluate_call(
        lambda: [grp.group_name for grp in GroupService.all(models.Group, db_session=db_session)],
        http_error=HTTPForbidden, msg_on_fail=s.Groups_GET_ForbiddenResponseSchema.description)
    return group_names


def get_group_resources(group, db_session):
    # type: (models.Group, Session) -> JSON
    """
    Get formatted JSON body describing all service resources the ``group`` as permissions on.
    """
    json_response = {}
    for svc in list(ResourceService.all(models.Service, db_session=db_session)):
        svc_perms = get_group_service_permissions(group=group, service=svc, db_session=db_session)
        svc_name = str(svc.resource_name)
        svc_type = str(svc.type)
        if svc_type not in json_response:
            json_response[svc_type] = {}
        res_perm_dict = get_group_service_resources_permissions_dict(group=group, service=svc, db_session=db_session)
        json_response[svc_type][svc_name] = format_service_resources(
            svc,
            db_session=db_session,
            service_perms=svc_perms,
            resources_perms_dict=res_perm_dict,
            show_all_children=False,
            show_private_url=False,
        )
    return json_response


def create_group(group_name, description, discoverable, db_session):
    # type: (Str, Str, bool, Session) -> HTTPException
    """
    Creates a group if it is permitted and not conflicting.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    description = str(description) if description else None
    discoverable = asbool(discoverable)
    group_content_error = {
        "group_name": str(group_name),
        "description": description,
        "discoverable": discoverable
    }
    ax.verify_param(group_name, matches=True, param_compare=ax.PARAM_REGEX, param_name="group_name",
                    http_error=HTTPBadRequest, content=group_content_error,
                    msg_on_fail=s.Groups_POST_BadRequestResponseSchema.description)
    if description:
        ax.verify_param(description, matches=True, param_compare=ax.PARAM_REGEX, param_name="description",
                        http_error=HTTPBadRequest, content=group_content_error,
                        msg_on_fail=s.Groups_POST_BadRequestResponseSchema.description)

    group = GroupService.by_group_name(group_name, db_session=db_session)
    ax.verify_param(group, is_none=True, param_name="group_name", with_param=False,  # don't return group as value
                    http_error=HTTPConflict, content=group_content_error,
                    msg_on_fail=s.Groups_POST_ConflictResponseSchema.description)
    new_group = ax.evaluate_call(
        lambda: models.Group(group_name=group_name, description=description, discoverable=discoverable),  # noqa
        fallback=lambda: db_session.rollback(), http_error=HTTPForbidden, content=group_content_error,
        msg_on_fail=s.Groups_POST_ForbiddenCreateResponseSchema.description)
    ax.evaluate_call(lambda: db_session.add(new_group), fallback=lambda: db_session.rollback(),
                     http_error=HTTPForbidden, content=group_content_error,
                     msg_on_fail=s.Groups_POST_ForbiddenAddResponseSchema.description)
    return ax.valid_http(http_success=HTTPCreated, detail=s.Groups_POST_CreatedResponseSchema.description,
                         content={"group": format_group(new_group, basic_info=True)})


def create_group_resource_permission_response(group, resource, permission, db_session):
    # type: (models.Group, ServiceOrResourceType, PermissionSet, Session) -> HTTPException
    """
    Creates a permission on a group/resource combination if it is permitted and not conflicting.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    resource_id = resource.resource_id
    check_valid_service_or_resource_permission(permission.name, resource, db_session)
    perm_content = {"permission_name": str(permission), "permission": permission.json(),
                    "resource": format_resource(resource, basic_info=True),
                    "group": format_group(group, basic_info=True)}
    existing_perm = ax.evaluate_call(
        lambda: GroupResourcePermissionService.get(group.id, resource_id, str(permission), db_session=db_session),
        fallback=lambda: db_session.rollback(), http_error=HTTPForbidden,
        msg_on_fail=s.GroupResourcePermissions_POST_ForbiddenGetResponseSchema.description, content=perm_content
    )
    ax.verify_param(existing_perm, is_none=True, http_error=HTTPConflict, content=perm_content,
                    msg_on_fail=s.GroupResourcePermissions_POST_ConflictResponseSchema.description)
    new_perm = ax.evaluate_call(
        lambda: models.GroupResourcePermission(resource_id=resource_id, group_id=group.id, perm_name=str(permission)),
        fallback=lambda: db_session.rollback(), http_error=HTTPForbidden, content=perm_content,
        msg_on_fail=s.GroupResourcePermissions_POST_ForbiddenCreateResponseSchema.description)
    ax.evaluate_call(lambda: db_session.add(new_perm), fallback=lambda: db_session.rollback(),
                     http_error=HTTPForbidden, content=perm_content,
                     msg_on_fail=s.GroupResourcePermissions_POST_ForbiddenAddResponseSchema.description)
    return ax.valid_http(http_success=HTTPCreated, content=perm_content,
                         detail=s.GroupResourcePermissions_POST_CreatedResponseSchema.description)


def get_group_resources_permissions_dict(group, db_session, resource_ids=None, resource_types=None):
    # type: (models.Group, Session, Optional[Iterable[int]], Optional[Iterable[Str]]) -> JSON
    """
    Get a dictionary of resources and corresponding permissions that a group has on the resources.

    Filter search by ``resource_ids`` and/or ``resource_types`` if specified.
    """
    def get_grp_res_perm(grp, db, res_ids, res_types):
        res_perms_tup = GroupService.resources_with_possible_perms(
            grp, resource_ids=res_ids, resource_types=res_types, db_session=db)
        res_perms_dict = {}
        for res_perm in res_perms_tup:
            if res_perm.resource.resource_id not in res_perms_dict:
                res_perms_dict[res_perm.resource.resource_id] = [res_perm.perm_name]
            else:
                res_perms_dict[res_perm.resource.resource_id].append(res_perm.perm_name)
        return res_perms_dict

    return ax.evaluate_call(lambda: get_grp_res_perm(group, db_session, resource_ids, resource_types),
                            fallback=lambda: db_session.rollback(),
                            http_error=HTTPInternalServerError,
                            msg_on_fail=s.GroupResourcesPermissions_InternalServerErrorResponseSchema.description,
                            content={"group": repr(group), "resource_ids": repr(resource_ids),
                                     "resource_types": repr(resource_types)})


def get_group_resource_permissions_response(group, resource, db_session):
    # type: (models.Group, models.Resource, Session) -> HTTPException
    """
    Get validated response with group resource permissions as content.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    def get_grp_res_perms(grp, res, db):
        if res.owner_group_id == grp.id:
            # FIXME: no 'magpie.models.Resource.permissions' - ok for now because no owner handling...
            return models.RESOURCE_TYPE_DICT[res.type].permissions
        perms = db.query(models.GroupResourcePermission) \
                  .filter(models.GroupResourcePermission.resource_id == res.resource_id) \
                  .filter(models.GroupResourcePermission.group_id == grp.id)
        return [PermissionSet.convert(p) for p in perms]

    group_permissions = ax.evaluate_call(
        lambda: format_permissions(get_grp_res_perms(group, resource, db_session), PermissionType.INHERITED),
        http_error=HTTPInternalServerError,
        msg_on_fail=s.GroupResourcePermissions_InternalServerErrorResponseSchema.description,
        content={"group": repr(group), "resource": repr(resource)})
    return ax.valid_http(http_success=HTTPOk, detail=s.GroupResourcePermissions_GET_OkResponseSchema.description,
                         content=group_permissions)


def delete_group_resource_permission_response(group, resource, permission, db_session):
    # type: (models.Group, ServiceOrResourceType, PermissionSet, Session) -> HTTPException
    """
    Get validated response on deleted group resource permission.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    resource_id = resource.resource_id
    check_valid_service_or_resource_permission(permission.name, resource, db_session)
    perm_content = {"permission_name": str(permission), "permission": permission.json(),
                    "resource": format_resource(resource, basic_info=True),
                    "group": format_group(group, basic_info=True)}
    del_perm = ax.evaluate_call(
        lambda: GroupResourcePermissionService.get(group.id, resource_id, str(permission), db_session=db_session),
        fallback=lambda: db_session.rollback(), http_error=HTTPForbidden,
        msg_on_fail=s.GroupServicePermission_DELETE_ForbiddenGetResponseSchema.description, content=perm_content
    )
    ax.verify_param(del_perm, not_none=True, http_error=HTTPNotFound, content=perm_content,
                    msg_on_fail=s.GroupServicePermission_DELETE_NotFoundResponseSchema.description)
    ax.evaluate_call(lambda: db_session.delete(del_perm), fallback=lambda: db_session.rollback(),
                     http_error=HTTPForbidden, content=perm_content,
                     msg_on_fail=s.GroupServicePermission_DELETE_ForbiddenResponseSchema.description)
    return ax.valid_http(http_success=HTTPOk, detail=s.GroupServicePermission_DELETE_OkResponseSchema.description)


def get_group_services(resources_permissions_dict, db_session):
    # type: (JSON, Session) -> JSON
    """
    Nest and regroup the resource permissions under corresponding root service types.
    """
    grp_svc_dict = {}
    for res_id, perms in resources_permissions_dict.items():
        svc = ResourceService.by_resource_id(resource_id=res_id, db_session=db_session)
        svc_type = str(svc.type)
        svc_name = str(svc.resource_name)
        if svc_type not in grp_svc_dict:
            grp_svc_dict[svc_type] = {}
        grp_svc_dict[svc_type][svc_name] = format_service(svc, perms, show_private_url=False)
    return grp_svc_dict


def get_group_services_response(group, db_session):
    # type: (models.Group, Session) -> HTTPException
    """
    Get validated response of services the group has permissions on.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    res_perm_dict = get_group_resources_permissions_dict(group,
                                                         resource_types=[models.Service.resource_type_name],
                                                         db_session=db_session)
    grp_svc_json = ax.evaluate_call(lambda: get_group_services(res_perm_dict, db_session),
                                    http_error=HTTPInternalServerError,
                                    msg_on_fail=s.GroupServices_InternalServerErrorResponseSchema.description,
                                    content={"group": format_group(group, basic_info=True)})
    return ax.valid_http(http_success=HTTPOk, detail=s.GroupServices_GET_OkResponseSchema.description,
                         content={"services": grp_svc_json})


def get_group_service_permissions(group, service, db_session):
    # type: (models.Group, models.Service, Session) -> List[PermissionSet]
    """
    Get all permissions the group has on a specific service.
    """
    def get_grp_svc_perms(grp, svc, db):
        if svc.owner_group_id == grp.id:
            return SERVICE_TYPE_DICT[svc.type].permissions
        perms = db.query(models.GroupResourcePermission) \
                  .filter(models.GroupResourcePermission.resource_id == svc.resource_id) \
                  .filter(models.GroupResourcePermission.group_id == grp.id)
        return format_permissions(perms, PermissionType.ALLOWED)

    return ax.evaluate_call(lambda: get_grp_svc_perms(group, service, db_session),
                            http_error=HTTPInternalServerError,
                            msg_on_fail="Failed to obtain group service permissions",
                            content={"group": repr(group), "service": repr(service)})


def get_group_service_permissions_response(group, service, db_session):
    # type: (models.Group, models.Service, Session) -> HTTPException
    """
    Get validated response of found group service permissions.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    svc_perms_found = ax.evaluate_call(
        lambda: format_permissions(get_group_service_permissions(group, service, db_session), PermissionType.APPLIED),
        http_error=HTTPInternalServerError,
        msg_on_fail=s.GroupServicePermissions_GET_InternalServerErrorResponseSchema.description,
        content={"group": format_group(group, basic_info=True), "service": format_service(service)})
    return ax.valid_http(http_success=HTTPOk, detail=s.GroupServicePermissions_GET_OkResponseSchema.description,
                         content=svc_perms_found)


def get_group_service_resources_permissions_dict(group, service, db_session):
    # type: (models.Group, models.Service, Session) -> ResourcePermissionMap
    """
    Get all permissions the group has on a specific service's children resources.
    """
    res_id = service.resource_id
    res_under_svc = models.RESOURCE_TREE_SERVICE.from_parent_deeper(parent_id=res_id, db_session=db_session)
    res_ids = [resource.Resource.resource_id for resource in res_under_svc]
    return get_group_resources_permissions_dict(group, db_session, resource_types=None, resource_ids=res_ids)


def get_group_service_resources_response(group, service, db_session):
    # type: (models.Group, models.Service, Session) -> HTTPException
    """
    Get validated response of all found service resources which the group has permissions on.

    :returns: valid HTTP response on successful operations.
    :raises HTTPException: error HTTP response of corresponding situation.
    """
    svc_perms = get_group_service_permissions(group=group, service=service, db_session=db_session)
    res_perms = get_group_service_resources_permissions_dict(group=group, service=service, db_session=db_session)
    svc_res_json = format_service_resources(
        service=service,
        db_session=db_session,
        service_perms=svc_perms,
        resources_perms_dict=res_perms,
        show_all_children=False,
        show_private_url=False,
    )
    return ax.valid_http(http_success=HTTPOk, detail=s.GroupServiceResources_GET_OkResponseSchema.description,
                         content={"service": svc_res_json})
