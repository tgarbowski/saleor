import django_filters
import graphene

from .enums import WmsDocumentStatusFilter, WmsDocumentTypeFilter
from saleor.graphql.core.filters import ListObjectTypeFilter, ObjectTypeFilter
from saleor.graphql.core.types import FilterInputObjectType
from saleor.wms import models


def filter_document_type(qs, _, value):
    query_objects = qs.none()
    if value:
        query_objects |= qs.filter(document_type__in=value)
    return query_objects


def filter_created_by(qs, _, value):
    return qs.filter(created_by=value.get("created_by"))


def filter_status(qs, _, value):
    query_objects = qs.none()
    if value:
        query_objects |= qs.filter(status__in=value)
    return query_objects


def filter_recipient(qs, _, value):
    return qs.filter(recipient=value.get("recipient"))


def filter_document(qs, _, value):
    document_id = graphene.Node.from_global_id(value['document'])[1]
    return qs.filter(document=document_id)


def filter_location(qs, _, value):
    return qs.filter(location=value.get("location"))


class DocumentTypeInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document type for warehouse document", required=False)


class CreatedByInput(graphene.InputObjectType):
    user_id = graphene.ID(description="user id", required=False)


class StatusInput(graphene.InputObjectType):
    status = graphene.String(description="Status of warehouse documents", required=False)


class RecipientInput(graphene.InputObjectType):
    recipient = graphene.String(description="Recipient of warehouse documents", required=False)


class DocumentInput(graphene.InputObjectType):
    document = graphene.String(description="Document of warehouse positions", required=False)


class LocationInput(graphene.InputObjectType):
    location = graphene.String(description="Location for warehouse document", required=False)


class WmsDocumentFilter(django_filters.FilterSet):
    document_type = ListObjectTypeFilter(input_class=WmsDocumentTypeFilter, method=filter_document_type)
    created_by = ObjectTypeFilter(input_class=CreatedByInput, method=filter_created_by)
    status = ListObjectTypeFilter(input_class=WmsDocumentStatusFilter, method=filter_status)
    recipient = ObjectTypeFilter(input_class=RecipientInput, method=filter_recipient)
    location = ObjectTypeFilter(input_class=LocationInput, method=filter_location)

    class Meta:
        model = models.WmsDocument
        fields = [
            "created_by",
            "document_type",
            "status",
            "recipient"
        ]


class WmsDocumentFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WmsDocumentFilter


class WmsDocPositionFilter(django_filters.FilterSet):
    document = ObjectTypeFilter(input_class=DocumentInput, method=filter_document)

    class Meta:
        model = models.WmsDocPosition
        fields = [
            "document"
        ]


class WmsDocPositionFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WmsDocPositionFilter

