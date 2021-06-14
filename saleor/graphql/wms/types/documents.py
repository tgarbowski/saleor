from graphene_federation import key
from saleor.graphql.core.connection import CountableDjangoObjectType
from saleor.wms import models


@key(fields="id")
class WMSDocument(CountableDjangoObjectType):

    class Meta:
        description = (
            "Represents a wms document")
        model = models.WMSDocument
        only_fields = ["created_at", "updated_at", "warehouse", "document_type", "created_by",
                       "recipient", "deliverer", "number", "status", "id"]


@key(fields="id")
class WMSDocPosition(CountableDjangoObjectType):

    class Meta:
        description = (
            "Represents a wms document")
        model = models.WMSDocPosition
        only_fields = ["product_variant", "quantity", "weight", "document", "id"]
