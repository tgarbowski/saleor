import django_filters
import graphene
from graphene_django.filter import GlobalIDMultipleChoiceFilter

from saleor.wms import models

from saleor.graphql.core.filters import ObjectTypeFilter

from saleor.graphql.core.types import FilterInputObjectType


def filter_document_type(qs, _, value):
    return qs.filter(document_type=value.get("document_type"))


class DocumentTypeInput(graphene.InputObjectType):
    document_type = graphene.String(description="Document type for warehouse document", required=False)


class WMSDocumentFilter(django_filters.FilterSet):
    document_type = ObjectTypeFilter(input_class=DocumentTypeInput, method=filter_document_type)
    ids = GlobalIDMultipleChoiceFilter(field_name="id")

    class Meta:
        model = models.WMSDocument
        fields = [
            "created_by",
        ]


class WMSDocumentFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = WMSDocumentFilter
