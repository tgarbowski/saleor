import graphene

from django.core.exceptions import ValidationError
from saleor.graphql.core.mutations import ModelDeleteMutation, ModelMutation
from .types import WMSDocumentInput, WMSDocPositionInput
from saleor.wms import models
from saleor.core.permissions import ProductPermissions
from saleor.graphql.core.types.common import WMSDocumentError
from saleor.core.exceptions import PermissionDenied
from saleor.plugins.manager import get_plugins_manager


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
        error_type_field = "wms_errors"

    @classmethod
    def save(cls, info, instance, cleaned_input):
        document_number = WMSDocumentCreate.create_document_number(instance.document_type)
        instance.number = document_number
        instance.save()

    @staticmethod
    def create_document_number(document_type):
        configuration = WMSDocumentCreate.get_plugin_config('WMS')
        user_document_type = configuration.get(document_type)

        last_document = models.WMSDocument.objects.filter(document_type=document_type).order_by('id').last()
        if not last_document:
            return f'{user_document_type}1'
        last_document_number = last_document.number
        last_document_int = int(''.join(i for i in last_document_number if i.isdigit()))
        new_document_int = last_document_int + 1
        new_document_number = f'{user_document_type}{str(new_document_int)}'
        return new_document_number

    @staticmethod
    def get_plugin_config(plugin):
        manager = get_plugins_manager()
        plugin = manager.get_plugin(plugin)
        configuration = {item["name"]: item["value"] for item in plugin.configuration}
        return configuration


class WMSDocumentUpdate(ModelMutation):
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
        error_type_field = "wms_errors"


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
        error_type_field = "wms_errors"


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
        error_type_field = "wms_errors"

    @classmethod
    def save(cls, info, instance, cleaned_input):
        if instance.document.status == 'APPROVED':
            raise ValidationError(
                {
                    "docposition": ValidationError(
                        "You can't add or update position to accepted document"
                    )
                }
            )

        instance.save()


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
        error_type_field = "wms_errors"


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
        error_type_field = "wms_errors"
