from saleor.graphql.utils import get_user_or_app_from_context
from saleor.wms import models


def resolve_wms_documents(info, qs=None, **_kwargs):
    requestor = get_user_or_app_from_context(info.context)
    qs = qs or models.WMSDocument.objects.get_visible_to_user(requestor)
    return qs
