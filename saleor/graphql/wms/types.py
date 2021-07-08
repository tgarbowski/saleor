import graphene
from graphene_federation import key
from saleor.graphql.core.connection import CountableDjangoObjectType
from saleor.wms import models
from saleor.graphql.account.enums import CountryCodeEnum


class WmsDocumentInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document Type")
    deliverer = graphene.ID(description="Deliverer")
    status = graphene.String(description="Document status")
    recipient = graphene.ID(description="Recipient ID")
    created_by = graphene.ID(description="CreatedBy ID")
    warehouse = graphene.ID(description="Warehouse")
    warehouse_second = graphene.ID(description="Warehouse")
    location = graphene.String(description="Location")


@key(fields="id")
class WmsDocument(CountableDjangoObjectType):

    class Meta:
        description = ("Represents a wms document")
        model = models.WmsDocument
        interfaces = [graphene.relay.Node]
        only_fields = ["created_at", "updated_at", "warehouse", "document_type", "created_by",
                       "recipient", "deliverer", "number", "status", "id", "warehouse_second",
                       "location"]


@key(fields="id")
class WmsDocPosition(CountableDjangoObjectType):

    class Meta:
        description = ("Represents a wms document")
        model = models.WmsDocPosition
        interfaces = [graphene.relay.Node]
        only_fields = ["product_variant", "quantity", "weight", "document", "id"]


class WmsDocPositionInput(graphene.InputObjectType):
    quantity = graphene.Int(description="Quantity")
    weight = graphene.Float(description="Weight")
    document = graphene.ID(description="wms document")
    product_variant = graphene.ID(description="Product Variant")


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


@key(fields="id")
class WmsDeliverer(CountableDjangoObjectType):

    class Meta:
        description = ("Represents a wms deliverer")
        model = models.WmsDeliverer
        interfaces = [graphene.relay.Node]
        only_fields = ["company_name", "street", "city", "postal_code", "email", "vat_id",
                       "phone", "country", "first_name", "last_name"]
