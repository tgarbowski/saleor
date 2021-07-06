import graphene
from graphene_federation import key
from saleor.graphql.core.connection import CountableDjangoObjectType
from saleor.wms import models


class WmsDocumentInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document Type")
    deliverer = graphene.JSONString(description="Deliverer")
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

