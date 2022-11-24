import django_filters

from saleor.graphql.core.filters import ObjectTypeFilter
from saleor.graphql.core.types import FilterInputObjectType
from saleor.product.models import ProductType, Product
from saleor.graphql.meta.mutations import MetadataInput

def filter_product_type_metadata(qs, key, value):
    if not key or not value:
        return qs

    json_dict = {
        value.key: value.value
    }
    if key == 'private_metadata':
        qs = ProductType.objects.filter(private_metadata__contains=json_dict)
    elif key == 'metadata':
        qs = ProductType.objects.filter(metadata__contains=json_dict)

    return qs



class ProductTypeMetadataFilter(django_filters.FilterSet):

    # TODO: generic metadata filter to inherit from
    # def __init__(self):
    #     metaFileds = ["private_metadata", "metadata"]
    #     super().Meta.fields.extend(metaFileds)

    private_metadata = ObjectTypeFilter(input_class=MetadataInput,
                                        method=filter_product_type_metadata)
    metadata = ObjectTypeFilter(input_class=MetadataInput,
                                method=filter_product_type_metadata)

    class Meta:
        model = ProductType
        fields = ["private_metadata", "metadata"]


class ProductTypeMetadataFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = ProductTypeMetadataFilter


def filter_product_metadata(qs, key, value):
    if not key or not value:
        return qs

    json_dict = {
        value.key: value.value
    }
    if key == 'private_metadata':
        qs = Product.objects.filter(private_metadata__contains=json_dict)
    elif key == 'metadata':
        qs = Product.objects.filter(metadata__contains=json_dict)

    return qs

class ProductMetadataFilter(django_filters.FilterSet):

    private_metadata = ObjectTypeFilter(input_class=MetadataInput,
                                        method=filter_product_metadata)
    metadata = ObjectTypeFilter(input_class=MetadataInput,
                                method=filter_product_metadata)

    class Meta:
        model = Product
        fields = ["private_metadata", "metadata"]


class ProductMetadataFilterInput(FilterInputObjectType):
    class Meta:
        filterset_class = ProductMetadataFilter
