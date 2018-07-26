from magpie.api.api_rest_schemas import *
from magpie import MAGPIE_MODULE_DIR
import os


@SwaggerAPI.get(tags=[APITag])
@view_config(route_name=SwaggerAPI.name, renderer='templates/swagger_ui.mako', permission=NO_PERMISSION_REQUIRED)
def api_swagger(request):
    """
    Swagger UI route to display the Magpie REST API schemas.
    """
    swagger_versions_dir = '{}'.format(os.path.abspath(os.path.join(MAGPIE_MODULE_DIR, 'ui/swagger/versions')))
    return_data = {'api_title': TitleAPI,
                   'api_schema_path': SwaggerGenerator.path,
                   'api_schema_versions_dir': swagger_versions_dir}
    return return_data