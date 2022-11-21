import graphene

from django.core.exceptions import ValidationError

from saleor.graphql.core.mutations import BaseMutation
from saleor.core.permissions import ShippingPermissions
from saleor.shipping.error_codes import ShippingErrorCode
from saleor.graphql.core.types.common import ShippingError

from saleor.plugins.allegro.utils import get_allegro_channels_slugs
from saleor.plugins.allegro.tasks import change_allegro_order_status, update_allegro_tracking_number
from saleor.salingo.shipping import (
    create_shipping_information, get_fulfillment_by_package_id,
    shipment_strategy, update_tracking_number
)
from saleor.graphql.order.types import Fulfillment, Order


class PackageInput(graphene.InputObjectType):
    weight = graphene.Float(description="Weight", required=True)
    sizeX = graphene.Int(description="Width")
    sizeY = graphene.Int(description="Length")
    sizeZ = graphene.Int(description="Height")


class PackageCreateInput(graphene.InputObjectType):
    packageData = graphene.List(PackageInput, required=True)
    fulfillment = graphene.String(required=True, description="Order fullfilment ID")
    order = graphene.String(required=True, description="Order ID")


class PackageCreate(BaseMutation):
    packageId = graphene.Field(graphene.String, description='Package ID')

    class Arguments:
        input = PackageCreateInput(
            required=True,
            description=(
                "Client-side generated data required to create dpd package."
            ),
        )

    class Meta:
        description = "Creates a new package."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"

    @classmethod
    def validate_dimensions(cls, package, courier):
        """
        inpost paczkomat: A/B/C - max 41 X 38 X 64 cm, waga zawsze 25kg
        dpd kurier standard krajowy: max wymiar 150cm, suma wymiarow <= 300cm, 31,5kg
        gls pobranie: max wymiary 200cm, suma wymiarów < 300 cm, 31,5kg
        """
        for parcel in package:
            dimensions = [parcel['sizeX'], parcel['sizeY'], parcel['sizeZ']]
            dimensions_sum = sum(dimensions)
            weight = parcel['weight']
            max_dimension = max(dimensions)

            dimensions_error = ValidationError(
                {
                    "dimensions": ValidationError(
                        "Wrong weight/dimensions",
                        code=ShippingErrorCode.INVALID.value,
                    )
                }
            )

            if courier == "INPOST":
                if max_dimension > 64 or weight > 25:
                    raise dimensions_error
            if courier == "DPD":
                if max_dimension > 150 or weight > 31.5 or dimensions_sum > 300:
                    raise dimensions_error
            if courier == "GLS":
                if max_dimension > 200 or weight > 31.5 or dimensions_sum > 300:
                    raise dimensions_error

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        fulfillment_id = data['input']['fulfillment']
        order_id = data['input']['order']
        package = data['input']['packageData']

        order = graphene.Node.get_node_from_global_id(info, order_id, Order)
        fulfillment = graphene.Node.get_node_from_global_id(info, fulfillment_id, Fulfillment)
        shipping = create_shipping_information(order=order)
        courier = order.shipping_method.metadata.get("courier")
        cls.validate_dimensions(package, courier)

        package_id = shipment_strategy(courier=courier).create_package(
            shipping=shipping,
            package=package,
            fulfillment=fulfillment
        )

        return PackageCreate(packageId=package_id)


class LabelCreateInput(graphene.InputObjectType):
    package_id = graphene.Int(required=True)
    order = graphene.String(required=True, description="Order ID")


class LabelCreate(BaseMutation):
    label = graphene.Field(graphene.String, description='B64 label representation')

    class Arguments:
        input = LabelCreateInput(
            required=True,
            description=(
                "Client-side generated data required to create shipping label."
            ),
        )

    class Meta:
        description = "Generates a shipping label."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order_id = data['input']['order']
        order = graphene.Node.get_node_from_global_id(info, order_id, Order)
        courier = order.shipping_method.metadata.get("courier")
        package_id = data['input']['package_id']
        fulfillment = get_fulfillment_by_package_id(order=order, package_id=package_id)
        tracking_number = fulfillment.tracking_number
        """Some couriers create packages asynchronously and for dashboard flow we store
        package_id instead at first."""
        if tracking_number == str(package_id):
            update_tracking_number(order=order, package_id=package_id)

        label_b64 = shipment_strategy(courier=courier).generate_label(package_id=package_id)

        if label_b64 and order.channel.slug in get_allegro_channels_slugs():
            update_allegro_tracking_number(order=order)
            change_allegro_order_status(order=order, status="SENT")

        return LabelCreate(
            label=label_b64
        )
