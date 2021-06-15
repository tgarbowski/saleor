import graphene
from graphene_federation import key
from saleor.graphql.core.connection import CountableDjangoObjectType
from saleor.wms import models


class WMSDocumentInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document Type")
    deliverer = graphene.JSONString(description="Deliverer")
    number = graphene.String(description="Document number")
    status = graphene.String(description="Document status")
    recipient = graphene.Int(description="Recipient ID")
    created_by = graphene.Int(description="CreatedBy ID")
    warehouse = graphene.ID(required=False, description="Warehouse")


@key(fields="id")
class WMSDocument(CountableDjangoObjectType):

    class Meta:
        description = ("Represents a wms document")
        model = models.WMSDocument
        only_fields = ["created_at", "updated_at", "warehouse", "document_type", "created_by",
                       "recipient", "deliverer", "number", "status", "id"]


@key(fields="id")
class WMSDocPosition(CountableDjangoObjectType):

    class Meta:
        description = ("Represents a wms document")
        model = models.WMSDocPosition
        only_fields = ["product_variant", "quantity", "weight", "document", "id"]


class WMSDocPositionInput(graphene.InputObjectType):
    quantity = graphene.Int(description="Quantity")
    weight = graphene.Float(description="Weight")
    document = graphene.ID(description="WMS document")
    product_variant = graphene.ID(description="Product Variant")

