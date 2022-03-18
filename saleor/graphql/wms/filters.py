import django_filters
import graphene
from graphene_django.filter import GlobalIDMultipleChoiceFilter

from .enums import WmsDocumentStatusFilter, WmsDocumentTypeFilter
from saleor.graphql.core.filters import ListObjectTypeFilter, ObjectTypeFilter
from saleor.graphql.core.types import FilterInputObjectType
from saleor.graphql.core.types.common import DateRangeInput
from saleor.graphql.utils import get_nodes
from saleor.graphql.utils.filters import filter_range_field
from saleor.wms import models
from saleor.account.models import User
from saleor.warehouse.models import Warehouse
from saleor.graphql.utils.filters import filter_fields_containing_value


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


def filter_recipients(qs, _, value):
    if value:
        recipients = get_nodes(value, "User", User)
        qs = qs.filter(recipient__in=recipients)
    return qs


def filter_created_by(qs, _, value):
    if value:
        created_by = get_nodes(value, "User", User)
        qs = qs.filter(created_by__in=created_by)
    return qs


def filter_deliverers(qs, _, value):
    if value:
        deliverers = get_nodes(value, "WmsDeliverer", models.WmsDeliverer)
        qs = qs.filter(deliverer__in=deliverers)
    return qs


def filter_document(qs, _, value):
    document_id = graphene.Node.from_global_id(value['document'])[1]
    return qs.filter(document=document_id)


def filter_location(qs, _, value):
    return qs.filter(location=value)


def filter_created_at_range(qs, _, value):
    return filter_range_field(qs, "created_at__date", value)


def filter_updated_at_range(qs, _, value):
    return filter_range_field(qs, "updated_at__date", value)


def filter_warehouses(qs, _, value):
    if value:
        warehouses = get_nodes(value, "Warehouse", Warehouse)
        qs = qs.filter(warehouse__in=warehouses)
    return qs


class DocumentTypeInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document type for warehouse document", required=False)


class StatusInput(graphene.InputObjectType):
    status = graphene.String(description="Status of warehouse documents", required=False)


class DocumentInput(graphene.InputObjectType):
    document = graphene.String(description="Document of warehouse positions", required=False)


class LocationInput(graphene.InputObjectType):
    location = graphene.String(description="Location for warehouse document", required=False)


class WmsDocumentFilter(django_filters.FilterSet):
    document_type = ListObjectTypeFilter(input_class=WmsDocumentTypeFilter, method=filter_document_type)
    created_by = django_filters.CharFilter(method=filter_created_by)
    # recipients = GlobalIDMultipleChoiceFilter(method=filter_recipients)
    # deliverers = GlobalIDMultipleChoiceFilter(method=filter_deliverers)
    status = ListObjectTypeFilter(input_class=WmsDocumentStatusFilter, method=filter_status)
    location = django_filters.CharFilter(method=filter_location)
    created_at = ObjectTypeFilter(input_class=DateRangeInput, method=filter_created_at_range)
    updated_at = ObjectTypeFilter(input_class=DateRangeInput, method=filter_updated_at_range)
    # warehouse = GlobalIDMultipleChoiceFilter(method=filter_warehouses)
    search = django_filters.CharFilter(
        method=filter_fields_containing_value("number")
    )

    class Meta:
        model = models.WmsDocument
        fields = []


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


class WmsDelivererFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method=filter_fields_containing_value("company_name")
    )

    class Meta:
        model = models.WmsDeliverer
        fields = [
            "search"
        ]

class WmsDelivererFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WmsDelivererFilter
