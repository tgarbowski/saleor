import graphene

from saleor.graphql.account.types import User

from saleor.graphql.product.types import (Product, ProductCountableConnection, ProductType,
                                          ProductTypeCountableConnection)
from saleor.graphql.core.connection import create_connection_slice, filter_connection_queryset
from saleor.graphql.core.fields import FilterConnectionField
from saleor.graphql.core.validators import validate_one_of_args_is_in_query

from .resolvers import (
    resolve_product_type_by_metadata,
    resolve_product_types_by_metadata,
    resolve_user_by_metadata, resolve_product_by_metadata)

from .filters import (
    ProductTypeMetadataFilterInput,
    ProductMetadataFilterInput)


class MetadataQueries(graphene.ObjectType):
    product_type_with_metadata = graphene.Field(
        ProductType,
        privateMetadataKey=graphene.String(),
        privateMetadataValue=graphene.String(),
        metadataKey=graphene.String(),
        metadataValue=graphene.String()
    )

    product_types_with_metadata = FilterConnectionField(
        ProductTypeCountableConnection,
        filter=ProductTypeMetadataFilterInput(
            description="Filtering options for product types with metadata."
        ),
        description="List of the shop's product types.",
    )

    user_with_metadata = graphene.Field(
        User,
        privateMetadataKey=graphene.String(),
        privateMetadataValue=graphene.String(),
        metadataKey=graphene.String(),
        metadataValue=graphene.String()
    )

    product_with_metadata = graphene.Field(
        Product,
        privateMetadataKey=graphene.String(),
        privateMetadataValue=graphene.String(),
        metadataKey=graphene.String(),
        metadataValue=graphene.String()
    )

    products_with_metadata = FilterConnectionField(
        ProductCountableConnection,
        filter=ProductMetadataFilterInput(
            description="Filtering options for products with metadata."
        ),
        description="List of the shop's products.",
    )



    def resolve_product_type_with_metadata(self, info, privateMetadataKey=None, metadataKey=None,
                                           privateMetadataValue=None, metadataValue=None):
        validate_one_of_args_is_in_query("privateMetadataKey", privateMetadataKey, "metadataKey", metadataKey)

        return resolve_product_type_by_metadata(privateMetadataKey, metadataKey,
                                                privateMetadataValue, metadataValue)

    def resolve_product_types_with_metadata(self, info, **kwargs):
        qs = resolve_product_types_by_metadata()
        qs = filter_connection_queryset(qs, kwargs)
        return create_connection_slice(qs, info, kwargs, ProductTypeCountableConnection)


    def resolve_user_with_metadata(self, info, privateMetadataKey=None, metadataKey=None,
                                           privateMetadataValue=None, metadataValue=None):
        validate_one_of_args_is_in_query("privateMetadataKey", privateMetadataKey, "metadataKey", metadataKey)

        return resolve_user_by_metadata(privateMetadataKey, metadataKey,
                                                privateMetadataValue, metadataValue)


    def resolve_product_with_metadata(self, info, privateMetadataKey=None, metadataKey=None,
                                           privateMetadataValue=None, metadataValue=None):
        validate_one_of_args_is_in_query("privateMetadataKey", privateMetadataKey, "metadataKey", metadataKey)

        return resolve_product_by_metadata(privateMetadataKey, metadataKey,
                                                privateMetadataValue, metadataValue)


