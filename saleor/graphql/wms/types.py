import graphene

from saleor.graphql.core.connection import CountableConnection
from saleor.wms import models
from saleor.graphql.account.enums import CountryCodeEnum
from saleor.graphql.channel import ChannelContext
from saleor.graphql.core.types import ModelObjectType
from saleor.graphql.warehouse.types import Warehouse
from saleor.graphql.account.types import User
from saleor.graphql.product.types import ProductVariant


class WmsDelivererInput(graphene.InputObjectType):
    company_name = graphene.String(description="Company name")
    street = graphene.String(description="Street")
    city = graphene.String(description="City")
    postal_code = graphene.String(description="Postal Code")
    email = graphene.String(description="Email")
    vat_id = graphene.String(description="VAT ID")
    phone = graphene.String(description="Phone")
    country = CountryCodeEnum(description="Country")
    first_name = graphene.String(description="First name")
    last_name = graphene.String(description="Last name")


class WmsDeliverer(ModelObjectType):
    id = graphene.GlobalID()
    company_name = graphene.String(description="Company name")
    street = graphene.String(description="Street")
    city = graphene.String(description="City")
    postal_code = graphene.String(description="Postal Code")
    email = graphene.String(description="Email")
    vat_id = graphene.String(description="VAT ID")
    phone = graphene.String(description="Phone")
    country = CountryCodeEnum(description="Country")
    first_name = graphene.String(description="First name")
    last_name = graphene.String(description="Last name")

    class Meta:
        description = "Represents a wms deliverer"
        model = models.WmsDeliverer
        interfaces = [graphene.relay.Node]


class WMSDelivererCountableConnection(CountableConnection):
    class Meta:
        node = WmsDeliverer


class WmsDocumentInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document Type")
    deliverer = graphene.ID(description="Deliverer")
    status = graphene.String(description="Document status")
    recipient = graphene.ID(description="Recipient ID")
    created_by = graphene.ID(description="CreatedBy ID")
    warehouse = graphene.ID(description="Warehouse")
    warehouse_second = graphene.ID(description="Warehouse")
    location = graphene.String(description="Location")


class WmsDocument(ModelObjectType):
    id = graphene.GlobalID()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()
    warehouse = graphene.Field(Warehouse)
    warehouse_second = graphene.Field(Warehouse)
    document_type = graphene.String()
    created_by = graphene.Field(User)
    recipient = graphene.Field(User)
    deliverer = graphene.Field(WmsDeliverer)
    number = graphene.String()
    status = graphene.String()
    location = graphene.String()

    class Meta:
        description = "Represents a wms document"
        model = models.WmsDocument
        interfaces = [graphene.relay.Node]


class WMSDocumentCountableConnection(CountableConnection):
    class Meta:
        node = WmsDocument


class WmsDocPosition(ModelObjectType):
    id = graphene.GlobalID()
    product_variant = graphene.Field(ProductVariant)
    quantity = graphene.Int()
    weight = graphene.Float()
    document = graphene.Field(WmsDocument)

    class Meta:
        description = "Represents a wms document"
        model = models.WmsDocPosition
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_product_variant(root: models.WmsDocPosition, info):
        return ChannelContext(node=root.product_variant, channel_slug=None)


class WmsDocPositionInput(graphene.InputObjectType):
    quantity = graphene.Int(description="Quantity")
    weight = graphene.Float(description="Weight")
    document = graphene.ID(description="wms document")
    product_variant = graphene.ID(description="Product Variant")


class WMSDocPositionCountableConnection(CountableConnection):
    class Meta:
        node = WmsDocPosition
