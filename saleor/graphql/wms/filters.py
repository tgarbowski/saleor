import django_filters
import graphene

from .enums import WMSDocumentStatusFilter, WMSDocumentTypeFilter
from saleor.graphql.core.filters import ListObjectTypeFilter, ObjectTypeFilter
from saleor.graphql.core.types import FilterInputObjectType
from saleor.wms import models


def filter_document_type(qs, _, value):
    #return qs.filter(document_type=value.get("document_type"))
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
    return qs.filter(document=value.get("document"))


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


class WMSDocumentFilter(django_filters.FilterSet):
    document_type = ListObjectTypeFilter(input_class=WMSDocumentTypeFilter, method=filter_document_type)
    created_by = ObjectTypeFilter(input_class=CreatedByInput, method=filter_created_by)
    status = ListObjectTypeFilter(input_class=WMSDocumentStatusFilter, method=filter_status)
    recipient = ObjectTypeFilter(input_class=RecipientInput, method=filter_recipient)

    class Meta:
        model = models.WMSDocument
        fields = [
            "created_by",
            "document_type",
            "status",
            "recipient"
        ]


class WMSDocumentFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WMSDocumentFilter


class WMSDocPositionFilter(django_filters.FilterSet):
    document = ObjectTypeFilter(input_class=DocumentInput, method=filter_document)

    class Meta:
        model = models.WMSDocPosition
        fields = [
            "document"
        ]


class WMSDocPositionFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WMSDocPositionFilter

