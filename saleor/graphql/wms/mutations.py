import graphene

from django.core.exceptions import ValidationError

from saleor.graphql.core.mutations import ModelDeleteMutation, ModelMutation
from .types import WmsDelivererInput, WmsDocumentInput, WmsDocPositionInput
from saleor.wms import models
from saleor.core.permissions import WMSPermissions
from saleor.graphql.core.types.common import WmsDocumentError
from saleor.plugins.manager import get_plugins_manager
from saleor.wms.error_codes import WmsErrorCode


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
    def clean_input(cls, info, instance, data):
        cleaned_input = super().clean_input(info, instance, data)
        location = cleaned_input.get("location")
        document_type = cleaned_input.get("document_type")
        warehouse_second = cleaned_input.get("warehouse_second")

        WmsDocumentCreate.validate_wms_location(location, document_type)
        WmsDocumentCreate.validate_wms_second_warehouse(warehouse_second, document_type)

        return cleaned_input

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

    @staticmethod
    def validate_wms_location(location, document_type):
        if not location and document_type in ["FGTN", "IO"]:
            raise ValidationError(
                {
                    "location": ValidationError(
                        "Location is necessary for FGTN and IO documents"
                    )
                }
            )

    @staticmethod
    def validate_wms_second_warehouse(warehouse_second, document_type):
        if not warehouse_second and document_type == "IWM":
            raise ValidationError(
                {
                    "second_warehouse": ValidationError(
                        "Second warehouse is necessary for IWM documents"
                    )
                }
            )


class WmsDocumentUpdate(WmsDocumentCreate):
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

    @classmethod
    def save(cls, info, instance, cleaned_input):
        location = instance.location
        document_type = instance.document_type
        WmsDocumentCreate.validate_wms_location(location, document_type)
        instance.save()

    @classmethod
    def clean_input(cls, info, instance, data):
        cleaned_input = super().clean_input(info, instance, data)
        document_type = cleaned_input.get('document_type')

        if document_type and document_type != instance.document_type:
            instance.number = WmsDocumentCreate.create_document_number(document_type)

        return cleaned_input


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
    def clean_input(cls, info, instance, data):
        cleaned_input = super().clean_input(info, instance, data)
        weight = cleaned_input.get("weight")
        quantity = cleaned_input.get("quantity")

        if weight and weight < 0:
            raise ValidationError(
                {
                    "weight": ValidationError(
                        "Document position can't have negative weight.",
                        code=WmsErrorCode.INVALID,
                    )
                }
            )
        if quantity and quantity < 0:
            raise ValidationError(
                {
                    "quantity": ValidationError(
                        "Document position can't have negative quantity.",
                        code=WmsErrorCode.INVALID,
                    )
                }
            )

        return cleaned_input

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


class WmsDelivererCreate(ModelMutation):
    class Arguments:
        input = WmsDelivererInput(
            required=True, description="Fields required to create a WMS deliverer."
        )

    class Meta:
        description = "Creates a new WMS deliverer."
        model = models.WmsDeliverer
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"


class WmsDelivererUpdate(ModelMutation):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a wms doc position to update.")
        input = WmsDelivererInput(
            required=True, description="Fields required to update a WMS deliverer."
        )

    class Meta:
        description = "Updates a new WMS deliverer."
        model = models.WmsDeliverer
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"


class WmsDelivererDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a wms deliverer to delete."
        )

    class Meta:
        description = "Updates a new WMS deliverer."
        model = models.WmsDeliverer
        permissions = (WMSPermissions.MANAGE_WMS,)
        error_type_class = WmsDocumentError
        error_type_field = "wms_errors"
