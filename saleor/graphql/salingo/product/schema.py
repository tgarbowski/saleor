import graphene

from .mutations import (
    ProductBulkClearWarehouseLocation, ProductMediaRetrieveFromBackup,
    ProductBulkPublish, UpdateMegapackPrivateMetadata
)
from saleor.graphql.core.fields import FilterConnectionField
from saleor.graphql.product.types.products import ProductVariantCountableConnection
from saleor.graphql.product.resolvers import resolve_product_variants_skus
from saleor.graphql.core.connection import create_connection_slice


class ProductQueries(graphene.ObjectType):
    product_variants_skus = FilterConnectionField(
        ProductVariantCountableConnection,
        sku=graphene.Argument(
            graphene.String, description="SKU matcher to get product_variants_count"
        ),
        description="Look for a mega pack SKU number"
    )
    def resolve_product_variants_skus(self, info, sku, **kwargs):
        qs = resolve_product_variants_skus(info, sku)

        return create_connection_slice(
            qs, info, kwargs, ProductVariantCountableConnection
        )

class ProductMutations(graphene.ObjectType):
    product_bulk_clear_warehouse_location = ProductBulkClearWarehouseLocation.Field()
    product_media_retrieve_from_backup = ProductMediaRetrieveFromBackup.Field()
    product_bulk_publish = ProductBulkPublish.Field()
    update_megapack_private_metadata = UpdateMegapackPrivateMetadata.Field()
