import graphene

from ...core.mutations import ModelDeleteMutation, ModelMutation
from ..types import WMSDocumentCreateInput, WMSInput, WMSDocPositionCreateInput, WMSDocPositionInput
from ....wms import models
from ....core.permissions import ProductPermissions
from ...core.types.common import ProductError


class WMSDocumentCreate(ModelMutation):
    class Arguments:
        input = WMSDocumentCreateInput(
            required=True, description="Fields required to create a WMS document."
        )

    class Meta:
        description = "Creates a new WMS document."
        model = models.WMSDocument
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"


class WMSDocumentUpdate(WMSDocumentCreate):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a WMSDocument to update.")
        input = WMSInput(
            required=True, description="Fields required to update a WMSDocument."
        )

    class Meta:
        description = "Updates an existing WMS document."
        model = models.WMSDocument
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"


class WMSDocPositionCreate(ModelMutation):
    class Arguments:
        input = WMSDocPositionCreateInput(
            required=True, description="Fields required to create a WMS doc position."
        )

    class Meta:
        description = "Creates a new WMS doc position."
        model = models.WMSDocPosition
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
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
        error_type_class = ProductError
        error_type_field = "product_errors"
