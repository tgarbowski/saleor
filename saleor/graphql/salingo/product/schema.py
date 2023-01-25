import graphene

from saleor.core.permissions import has_one_of_permissions
from saleor.page import models as pageModels
from saleor.product import models as productModels
from saleor.product.models import ALL_PRODUCTS_PERMISSIONS
from .mutations import (
    DeleteMegapackPrivateMetadata, ProductBulkClearWarehouseLocation, ProductMediaRetrieveFromBackup,
    ProductBulkPublish, UpdateMegapackPrivateMetadata
)
from saleor.graphql.core.fields import FilterConnectionField
from saleor.graphql.product.types.products import ProductVariantCountableConnection

from saleor.graphql.core.connection import create_connection_slice
from .types import SitemapSlugs
from ...channel.utils import get_default_channel_slug_or_graphql_error
from ...utils import get_user_or_app_from_context


class ProductQueries(graphene.ObjectType):
    product_variants_skus = FilterConnectionField(
        ProductVariantCountableConnection,
        sku=graphene.Argument(
            graphene.String, description="SKU matcher to get product_variants_count"
        ),
        description="Look for a mega pack SKU number"
    )
    sitemap_slugs = graphene.Field(
        SitemapSlugs,
        description="Look for a mega pack SKU number",
        channel=graphene.Argument(
            graphene.String,
            description="Slug of a channel for which the data should be returned."
        ),
        productsAmount=graphene.Argument(
            graphene.Int,
            description="Number of slugs to return"
        ),
        categoriesAmount = graphene.Argument(
            graphene.Int,
            description="Number of slugs to return"
        ),
        pagesAmount=graphene.Argument(
            graphene.Int,
            description="Number of slugs to return"
        )
    )

    def resolve_product_variants_skus(self, info, sku, **kwargs):
        qs = productModels.ProductVariant.objects.filter(sku__startswith=sku)

        return create_connection_slice(
            qs, info, kwargs, ProductVariantCountableConnection
        )

    def resolve_sitemap_slugs(self, info, channel, productsAmount, categoriesAmount,
                               pagesAmount):
        requestor = get_user_or_app_from_context(info.context)
        has_required_permissions = has_one_of_permissions(
            requestor, ALL_PRODUCTS_PERMISSIONS
        )
        if channel is None and not has_required_permissions:
            channel = get_default_channel_slug_or_graphql_error()
        productSlugs = productModels.Product.objects.visible_to_user(
            requestor, channel).order_by("id").values_list(
            'slug', flat=True)[:productsAmount]
        categoriesSlugs = productModels.Category.objects.order_by("id").values_list(
            'slug', flat=True)[:categoriesAmount]
        pagesSlugs = pageModels.Page.objects.order_by("id").values_list(
            'slug', flat=True)[:pagesAmount]

        return {"productSlugs": productSlugs, "categoriesSlugs": categoriesSlugs,
                "pagesSlugs": pagesSlugs}


class ProductMutations(graphene.ObjectType):
    product_bulk_clear_warehouse_location = ProductBulkClearWarehouseLocation.Field()
    product_media_retrieve_from_backup = ProductMediaRetrieveFromBackup.Field()
    product_bulk_publish = ProductBulkPublish.Field()
    update_megapack_private_metadata = UpdateMegapackPrivateMetadata.Field()
    delete_megapack_private_metadata = DeleteMegapackPrivateMetadata.Field()
