import graphene
from django.core.exceptions import ValidationError
from django.db import transaction

from ...core.permissions import ShippingPermissions
from ...shipping import models
from ...shipping.error_codes import ShippingErrorCode
from ...shipping.utils import (
    default_shipping_zone_exists,
    get_countries_without_shipping_zone,
)
from ..core.mutations import BaseMutation, ModelDeleteMutation, ModelMutation
from ..core.scalars import PositiveDecimal, WeightScalar
from ..core.types.common import ShippingError
from ..core.utils import get_duplicates_ids
from ..core.validators import validate_price_precision
from .enums import ShippingMethodTypeEnum
from .types import ShippingMethod, ShippingZone
from saleor.plugins.dpd.api import DpdApi
import base64
from saleor.graphql.order.types import Fulfillment


class ShippingPriceInput(graphene.InputObjectType):
    name = graphene.String(description="Name of the shipping method.")
    price = PositiveDecimal(description="Shipping price of the shipping method.")
    minimum_order_price = PositiveDecimal(
        description="Minimum order price to use this shipping method."
    )
    maximum_order_price = PositiveDecimal(
        description="Maximum order price to use this shipping method."
    )
    minimum_order_weight = WeightScalar(
        description="Minimum order weight to use this shipping method."
    )
    maximum_order_weight = WeightScalar(
        description="Maximum order weight to use this shipping method."
    )
    type = ShippingMethodTypeEnum(description="Shipping type: price or weight based.")
    shipping_zone = graphene.ID(
        description="Shipping zone this method belongs to.", name="shippingZone"
    )


class ShippingZoneCreateInput(graphene.InputObjectType):
    name = graphene.String(
        description="Shipping zone's name. Visible only to the staff."
    )
    countries = graphene.List(
        graphene.String, description="List of countries in this shipping zone."
    )
    default = graphene.Boolean(
        description=(
            "Default shipping zone will be used for countries not covered by other "
            "zones."
        )
    )
    add_warehouses = graphene.List(
        graphene.ID, description="List of warehouses to assign to a shipping zone",
    )


class ShippingZoneUpdateInput(ShippingZoneCreateInput):
    remove_warehouses = graphene.List(
        graphene.ID, description="List of warehouses to unassign from a shipping zone",
    )


class ShippingZoneMixin:
    @classmethod
    def clean_input(cls, info, instance, data, input_cls=None):
        duplicates_ids = get_duplicates_ids(
            data.get("add_warehouses"), data.get("remove_warehouses")
        )
        if duplicates_ids:
            error_msg = (
                "The same object cannot be in both lists "
                "for adding and removing items."
            )
            raise ValidationError(
                {
                    "removeWarehouses": ValidationError(
                        error_msg,
                        code=ShippingErrorCode.DUPLICATED_INPUT_ITEM.value,
                        params={"warehouses": list(duplicates_ids)},
                    )
                }
            )

        cleaned_input = super().clean_input(info, instance, data)
        cleaned_input = cls.clean_default(instance, cleaned_input)
        return cleaned_input

    @classmethod
    def clean_default(cls, instance, data):
        default = data.get("default")
        if default:
            if default_shipping_zone_exists(instance.pk):
                raise ValidationError(
                    {
                        "default": ValidationError(
                            "Default shipping zone already exists.",
                            code=ShippingErrorCode.ALREADY_EXISTS.value,
                        )
                    }
                )
            else:
                countries = get_countries_without_shipping_zone()
                data["countries"] = countries
        else:
            data["default"] = False
        return data

    @classmethod
    @transaction.atomic
    def _save_m2m(cls, info, instance, cleaned_data):
        super()._save_m2m(info, instance, cleaned_data)

        add_warehouses = cleaned_data.get("add_warehouses")
        if add_warehouses:
            instance.warehouses.add(*add_warehouses)

        remove_warehouses = cleaned_data.get("remove_warehouses")
        if remove_warehouses:
            instance.warehouses.remove(*remove_warehouses)


class ShippingZoneCreate(ShippingZoneMixin, ModelMutation):
    class Arguments:
        input = ShippingZoneCreateInput(
            description="Fields required to create a shipping zone.", required=True
        )

    class Meta:
        description = "Creates a new shipping zone."
        model = models.ShippingZone
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"


class ShippingZoneUpdate(ShippingZoneMixin, ModelMutation):
    class Arguments:
        id = graphene.ID(description="ID of a shipping zone to update.", required=True)
        input = ShippingZoneUpdateInput(
            description="Fields required to update a shipping zone.", required=True
        )

    class Meta:
        description = "Updates a new shipping zone."
        model = models.ShippingZone
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"


class ShippingZoneDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a shipping zone to delete.")

    class Meta:
        description = "Deletes a shipping zone."
        model = models.ShippingZone
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"


class ShippingPriceMixin:
    @classmethod
    def clean_input(cls, info, instance, data, input_cls=None):
        cleaned_input = super().clean_input(info, instance, data)

        # Rename the price field to price_amount (the model's)
        price_amount = cleaned_input.pop("price", None)
        if price_amount is not None:
            try:
                validate_price_precision(price_amount, instance.currency)
            except ValidationError as error:
                error.code = ShippingErrorCode.INVALID.value
                raise ValidationError({"price": error})
            cleaned_input["price_amount"] = price_amount

        cleaned_type = cleaned_input.get("type")
        if cleaned_type:
            if cleaned_type == ShippingMethodTypeEnum.PRICE.value:
                min_price = cleaned_input.pop("minimum_order_price", None)
                max_price = cleaned_input.pop("maximum_order_price", None)

                if min_price is not None:
                    try:
                        validate_price_precision(min_price, instance.currency)
                    except ValidationError as error:
                        error.code = ShippingErrorCode.INVALID.value
                        raise ValidationError({"minimum_order_price": error})
                    cleaned_input["minimum_order_price_amount"] = min_price

                if max_price is not None:
                    try:
                        validate_price_precision(max_price, instance.currency)
                    except ValidationError as error:
                        error.code = ShippingErrorCode.INVALID.value
                        raise ValidationError({"maximum_order_price": error})
                    cleaned_input["maximum_order_price_amount"] = max_price

                if (
                    min_price is not None
                    and max_price is not None
                    and max_price <= min_price
                ):
                    raise ValidationError(
                        {
                            "maximum_order_price": ValidationError(
                                (
                                    "Maximum order price should be larger than "
                                    "the minimum order price."
                                ),
                                code=ShippingErrorCode.MAX_LESS_THAN_MIN,
                            )
                        }
                    )
            else:
                min_weight = cleaned_input.get("minimum_order_weight")
                max_weight = cleaned_input.get("maximum_order_weight")

                if min_weight and min_weight.value < 0:
                    raise ValidationError(
                        {
                            "minimum_order_weight": ValidationError(
                                "Shipping can't have negative weight.",
                                code=ShippingErrorCode.INVALID,
                            )
                        }
                    )

                if max_weight and max_weight.value < 0:
                    raise ValidationError(
                        {
                            "maximum_order_weight": ValidationError(
                                "Shipping can't have negative weight.",
                                code=ShippingErrorCode.INVALID,
                            )
                        }
                    )

                if (
                    min_weight is not None
                    and max_weight is not None
                    and max_weight <= min_weight
                ):
                    raise ValidationError(
                        {
                            "maximum_order_weight": ValidationError(
                                (
                                    "Maximum order weight should be larger than the "
                                    "minimum order weight."
                                ),
                                code=ShippingErrorCode.MAX_LESS_THAN_MIN,
                            )
                        }
                    )
        return cleaned_input


class ShippingPriceCreate(ShippingPriceMixin, ModelMutation):
    shipping_zone = graphene.Field(
        ShippingZone,
        description="A shipping zone to which the shipping method belongs.",
    )

    class Arguments:
        input = ShippingPriceInput(
            description="Fields required to create a shipping price.", required=True
        )

    class Meta:
        description = "Creates a new shipping price."
        model = models.ShippingMethod
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"
        errors_mapping = {"price_amount": "price"}

    @classmethod
    def success_response(cls, instance):
        response = super().success_response(instance)
        response.shipping_zone = instance.shipping_zone
        return response


class ShippingPriceUpdate(ShippingPriceMixin, ModelMutation):
    shipping_zone = graphene.Field(
        ShippingZone,
        description="A shipping zone to which the shipping method belongs.",
    )

    class Arguments:
        id = graphene.ID(description="ID of a shipping price to update.", required=True)
        input = ShippingPriceInput(
            description="Fields required to update a shipping price.", required=True
        )

    class Meta:
        description = "Updates a new shipping price."
        model = models.ShippingMethod
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"
        errors_mapping = {"price_amount": "price"}

    @classmethod
    def success_response(cls, instance):
        response = super().success_response(instance)
        response.shipping_zone = instance.shipping_zone
        return response


class ShippingPriceDelete(BaseMutation):
    shipping_method = graphene.Field(
        ShippingMethod, description="A shipping method to delete."
    )
    shipping_zone = graphene.Field(
        ShippingZone,
        description="A shipping zone to which the shipping method belongs.",
    )

    class Arguments:
        id = graphene.ID(required=True, description="ID of a shipping price to delete.")

    class Meta:
        description = "Deletes a shipping price."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        shipping_method = cls.get_node_or_error(
            info, data.get("id"), only_type=ShippingMethod
        )
        shipping_method_id = shipping_method.id
        shipping_zone = shipping_method.shipping_zone
        shipping_method.delete()
        shipping_method.id = shipping_method_id
        return ShippingPriceDelete(
            shipping_method=shipping_method, shipping_zone=shipping_zone
        )


class PackageDataInput(graphene.InputObjectType):
    weight = graphene.Float(description="Weight", required=True)
    content = graphene.String(description="Content")
    customerData1 = graphene.String(description="Customer Data")
    sizeX = graphene.Int(description="Size X")
    sizeY = graphene.Int(description="Size Y")
    sizeZ = graphene.Int(description="Size Z")


class SenderDataInput(graphene.InputObjectType):
    address = graphene.String(required=True)
    city = graphene.String(required=True)
    company = graphene.String(required=True)
    countryCode = graphene.String(required=True)
    email = graphene.String(required=True)
    fid = graphene.String(required=True)
    phone = graphene.String(required=True)
    postalCode = graphene.String(required=True)


class ReceiverDataInput(graphene.InputObjectType):
    address = graphene.String(required=True)
    city = graphene.String(required=True)
    company = graphene.String(required=True)
    countryCode = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=True)
    postalCode = graphene.String(required=True)


class ServiceDataInput(graphene.InputObjectType):
    dox = graphene.Boolean(description="Envelope up to 0,5 kg")


class DpdCreatePackageInput(graphene.InputObjectType):
    reference = graphene.String()
    thirdPartyFID = graphene.Int(description="Third party FID")
    langCode = graphene.String(description="Language Code")
    packageData = graphene.List(PackageDataInput, required=True)
    senderData = SenderDataInput(required=True, description="Sender data.")
    receiverData = ReceiverDataInput(required=True)
    fulfillment = graphene.ID(required=True, description="Order fullfilment record ID")
    services = ServiceDataInput()


class DpdCreateLabelInput(graphene.InputObjectType):
    packageId = graphene.Int(required=True)
    senderData = SenderDataInput(required=True)


class DpdCreateProtocolInput(graphene.InputObjectType):
    waybills = graphene.List(graphene.String)
    packages = graphene.List(graphene.Int)
    senderData = SenderDataInput(required=True)


class DpdPackageCreate(BaseMutation):
    packageId = graphene.Int()
    parcelIds = graphene.List(graphene.Int)
    waybills = graphene.List(graphene.String)
    status = graphene.String()

    class Arguments:
        input = DpdCreatePackageInput(
            required=True,
            description=(
                "Client-side generated data required to create dpd package."
            ),
        )

    class Meta:
        description = "Creates a new shipping price."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        DPD_ApiInstance = DpdApi()

        package = DPD_ApiInstance.generate_package_shipment(
            packageData=data['input']['packageData'],
            receiverData=data['input']['receiverData'],
            senderData=data['input']['senderData'],
            servicesData=data['input'].get('services')
        )

        if package.Status != 'OK':
            return DpdPackageCreate(
                status=package.Status
            )

        package = package.Packages.Package[0]
        parcels = package.Parcels.Parcel
        parcel_ids = [parcel.ParcelId for parcel in package.Parcels.Parcel]
        waybills = [parcel.Waybill for parcel in package.Parcels.Parcel]
        new_parcels = []

        for parcel, response_parcel in zip(data['input']['packageData'], parcels):
            new_parcels.append(
                {
                    "id": response_parcel.ParcelId,
                    "waybill": response_parcel.Waybill,
                    "weight": parcel['weight'],
                    "sizeX": parcel['sizeX'],
                    "sizeY": parcel['sizeY'],
                    "sizeZ": parcel['sizeZ']
                }
            )

        json_package = {
            "status": package.Status,
            "id": package.PackageId,
            "parcels": new_parcels,
        }

        fulfillment_id = data['input']['fulfillment']
        fulfillment = graphene.Node.get_node_from_global_id(info, fulfillment_id, Fulfillment)
        fulfillment.store_value_in_private_metadata({'package': json_package})
        fulfillment.tracking_number = package.PackageId
        fulfillment.save()

        return DpdPackageCreate(
            packageId=package.PackageId,
            parcelIds=parcel_ids,
            waybills=waybills,
            status=package.Status
        )


class DpdLabelCreate(BaseMutation):
    label = graphene.Field(graphene.String, description='B64 label representation')

    class Arguments:
        input = DpdCreateLabelInput(
            required=True,
            description=(
                "Client-side generated data required to create dpd label."
            ),
        )

    class Meta:
        description = "Creates a new shipping price."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        DPD_ApiInstance = DpdApi()

        label = DPD_ApiInstance.generate_label(
            packageId=data['input']['packageId'],
            senderData=data['input']['senderData']
        )

        data = base64.b64encode(label['documentData']).decode('ascii')

        return DpdLabelCreate(
            label=data
        )


class DpdProtocolCreate(BaseMutation):
    protocol = graphene.Field(graphene.String, description='B64 protocol representation')

    class Arguments:
        input = DpdCreateProtocolInput(
            required=True,
            description=(
                "Client-side generated data required to create dpd label."
            ),
        )

    class Meta:
        description = "Creates a new shipping price."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        DPD_ApiInstance = DpdApi()

        protocol = DPD_ApiInstance.generate_protocol(
            waybills=data['input'].get('waybills'),
            packages=data['input'].get('packages'),
            senderData=data['input']['senderData']
        )
        data = base64.b64encode(protocol['documentData']).decode('ascii')

        return DpdProtocolCreate(
            protocol=data
        )
