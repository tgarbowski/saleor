import graphene

from django.core.exceptions import ValidationError
from saleor.graphql.core.mutations import ModelDeleteMutation, ModelMutation
from .types import WmsDocumentInput, WmsDocPositionInput
from saleor.wms import models
from saleor.core.permissions import WMSPermissions
from saleor.graphql.core.types.common import WmsDocumentError
from saleor.core.exceptions import PermissionDenied
from saleor.plugins.manager import get_plugins_manager


class WmsDocumentCreate(ModelMutation):
    class Arguments:
        input = WmsDocumentInput(
            required=True, description="Fields required to create a WMS document."
        )

    class Meta:
        description = "Creates a new WMS document."
        model = models.WmsDocument
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"

    @classmethod
    def save(cls, info, instance, cleaned_input):
        document_number = WmsDocumentCreate.create_document_number(instance.document_type)
        instance.number = document_number
        instance.save()

    @staticmethod
    def create_document_number(document_type):
        configuration = WmsDocumentCreate.get_plugin_config('WMS')
        user_document_type = configuration.get(document_type)

        last_document = models.WmsDocument.objects.filter(document_type=document_type).order_by('id').last()
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


class WmsDocumentUpdate(ModelMutation):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a WmsDocument to update.")
        input = WmsDocumentInput(
            required=True, description="Fields required to update a WmsDocument."
        )

    class Meta:
        description = "Updates an existing Wms document."
        model = models.WmsDocument
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"


class WmsDocumentDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a wms document to delete."
        )

    class Meta:
        description = "Deletes a wms document."
        model = models.WmsDocument
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"


class WmsDocPositionCreate(ModelMutation):
    class Arguments:
        input = WmsDocPositionInput(
            required=True, description="Fields required to create a wms doc position."
        )

    class Meta:
        description = "Creates a new wms doc position."
        model = models.WmsDocPosition
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
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


class WmsDocPositionUpdate(WmsDocPositionCreate):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a wms doc position to update.")
        input = WmsDocPositionInput(
            required=True, description="Fields required to update a wms doc position."
        )

    class Meta:
        description = "Updates an existing wms doc position."
        model = models.WmsDocPosition
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"


class WmsDocPositionDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a wms document position to delete."
        )

    class Meta:
        description = "Deletes a wms document position."
        model = models.WmsDocPosition
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"
