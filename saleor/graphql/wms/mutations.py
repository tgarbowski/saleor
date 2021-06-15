import graphene

from saleor.graphql.core.mutations import ModelDeleteMutation, ModelMutation
from .types import WMSDocumentInput, WMSDocPositionInput
from saleor.wms import models
from saleor.core.permissions import ProductPermissions
from saleor.graphql.core.types.common import WMSDocumentError
from saleor.core.exceptions import PermissionDenied


class WMSDocumentCreate(ModelMutation):
    class Arguments:
        input = WMSDocumentInput(
            required=True, description="Fields required to create a WMS document."
        )

    class Meta:
        description = "Creates a new WMS document."
        model = models.WMSDocument
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "product_errors"


class WMSDocumentUpdate(WMSDocumentCreate):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a WMSDocument to update.")
        input = WMSDocumentInput(
            required=True, description="Fields required to update a WMSDocument."
        )

    class Meta:
        description = "Updates an existing WMS document."
        model = models.WMSDocument
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "product_errors"


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


class WMSDocPositionCreate(ModelMutation):
    class Arguments:
        input = WMSDocPositionInput(
            required=True, description="Fields required to create a WMS doc position."
        )

    class Meta:
        description = "Creates a new WMS doc position."
        model = models.WMSDocPosition
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "product_errors"


class WMSDocPositionUpdate(WMSDocPositionCreate):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a WMS doc position to update.")
        input = WMSDocPositionInput(
            required=True, description="Fields required to update a WMS doc position."
        )

    class Meta:
        description = "Updates an existing WMS doc position."
        model = models.WMSDocPosition
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = WMSDocumentError
        error_type_field = "product_errors"


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
