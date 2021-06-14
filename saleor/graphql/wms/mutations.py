import graphene

from saleor.core.permissions import ProductPermissions
from saleor.graphql.core.mutations import ModelDeleteMutation
from saleor.graphql.core.types.common import WMSDocumentError
from saleor.wms import models

from saleor.core.exceptions import PermissionDenied


class WMSDocumentDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a wms document to delete."
        )

    class Meta:
        description = "Deletes a wms document."
        model = models.WMSDocument
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "wmsdocument_errors"


    @classmethod
    def perform_mutation(cls, _root, info, **data):
        if not cls.check_permissions(info.context):
            raise PermissionDenied()

        node_id = data.get("id")

        instance = models.WMSDocument.objects.get(pk=node_id)

        db_id = instance.id
        instance.delete()

        instance.id = db_id
        return cls.success_response(instance)


class WMSDocPositionDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a wms document position to delete."
        )

    class Meta:
        description = "Deletes a wms document position."
        model = models.WMSDocPosition
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "wmsdocument_errors"


    @classmethod
    def perform_mutation(cls, _root, info, **data):
        if not cls.check_permissions(info.context):
            raise PermissionDenied()

        node_id = data.get("id")

        instance = models.WMSDocPosition.objects.get(pk=node_id)

        db_id = instance.id
        instance.delete()

        instance.id = db_id
        return cls.success_response(instance)
