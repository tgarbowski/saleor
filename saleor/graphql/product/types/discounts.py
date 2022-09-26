import graphene
from graphene import relay

from saleor.discount import models
from ...channel import ChannelQsContext
from ...channel.dataloaders import ChannelByIdLoader
from ...channel.types import (
    Channel,
    ChannelContext,
    ChannelContextType,
    ChannelContextTypeWithMetadata,
)
from ...core.connection import CountableConnection, create_connection_slice
from ...core.descriptions import ADDED_IN_31
from ...core.fields import ConnectionField
from ...core.types import ModelObjectType, Money
from ...meta.types import ObjectWithMetadata
from ...product.types import (
    CategoryCountableConnection,
    CollectionCountableConnection,
    ProductCountableConnection,
    ProductVariantCountableConnection,
)
from ...translations.fields import TranslationField
from ...translations.types import SaleTranslation, VoucherTranslation
from ...discount.dataloaders import (
    SaleChannelListingBySaleIdAndChanneSlugLoader,
    SaleChannelListingBySaleIdLoader,
    VoucherChannelListingByVoucherIdAndChanneSlugLoader,
    VoucherChannelListingByVoucherIdLoader,
)
from ...discount.enums import (
    DiscountValueTypeEnum,
    OrderDiscountTypeEnum,
    SaleType,
    VoucherTypeEnum,
)


class SaleChannelListing(ModelObjectType):
    id = graphene.GlobalID(required=True)
    channel = graphene.Field(Channel, required=True)
    discount_value = graphene.Float(required=True)
    currency = graphene.String(required=True)

    class Meta:
        description = "Represents sale channel listing."
        model = models.SaleChannelListing
        interfaces = [relay.Node]

    @staticmethod
    def resolve_channel(root: models.SaleChannelListing, info, **_kwargs):
        return ChannelByIdLoader(info.context).load(root.channel_id)


class Sale(ChannelContextTypeWithMetadata, ModelObjectType):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    type = SaleType(required=True)
    start_date = graphene.DateTime(required=True)
    end_date = graphene.DateTime()
    created = graphene.DateTime(required=True)
    updated_at = graphene.DateTime(required=True)
    categories = ConnectionField(
        CategoryCountableConnection,
        description="List of categories this sale applies to.",
    )
    collections = ConnectionField(
        CollectionCountableConnection,
        description="List of collections this sale applies to.",
    )
    products = ConnectionField(
        ProductCountableConnection, description="List of products this sale applies to."
    )
    variants = ConnectionField(
        ProductVariantCountableConnection,
        description=f"{ADDED_IN_31} List of product variants this sale applies to.",
    )
    translation = TranslationField(
        SaleTranslation,
        type_name="sale",
        resolver=ChannelContextType.resolve_translation,
    )
    channel_listings = graphene.List(
        graphene.NonNull(SaleChannelListing),
        description="List of channels available for the sale.",
    )
    discount_value = graphene.Float(description="Sale value.")
    currency = graphene.String(description="Currency code for sale.")

    class Meta:
        default_resolver = ChannelContextType.resolver_with_context
        description = (
            "Sales allow creating discounts for categories, collections or products "
            "and are visible to all the customers."
        )
        interfaces = [relay.Node, ObjectWithMetadata]
        model = models.Sale

    @staticmethod
    def resolve_categories(root: ChannelContext[models.Sale], info, *_args, **kwargs):
        qs = root.node.categories.all()
        return create_connection_slice(qs, info, kwargs, CategoryCountableConnection)

    @staticmethod
    def resolve_channel_listings(root: ChannelContext[models.Sale], info, **_kwargs):
        return SaleChannelListingBySaleIdLoader(info.context).load(root.node.id)

    @staticmethod
    def resolve_collections(root: ChannelContext[models.Sale], info, *_args, **kwargs):
        qs = root.node.collections.all()
        qs = ChannelQsContext(qs=qs, channel_slug=root.channel_slug)
        return create_connection_slice(qs, info, kwargs, CollectionCountableConnection)

    @staticmethod
    def resolve_products(root: ChannelContext[models.Sale], info, **kwargs):
        qs = root.node.products.all()
        qs = ChannelQsContext(qs=qs, channel_slug=root.channel_slug)
        return create_connection_slice(qs, info, kwargs, ProductCountableConnection)

    @staticmethod
    def resolve_variants(root: ChannelContext[models.Sale], info, **kwargs):
        qs = root.node.variants.all()
        qs = ChannelQsContext(qs=qs, channel_slug=root.channel_slug)
        return create_connection_slice(
            qs, info, kwargs, ProductVariantCountableConnection
        )

    @staticmethod
    def resolve_discount_value(root: ChannelContext[models.Sale], info, **_kwargs):
        if not root.channel_slug:
            return None

        return (
            SaleChannelListingBySaleIdAndChanneSlugLoader(info.context)
            .load((root.node.id, root.channel_slug))
            .then(
                lambda channel_listing: channel_listing.discount_value
                if channel_listing
                else None
            )
        )

    @staticmethod
    def resolve_currency(root: ChannelContext[models.Sale], info, **_kwargs):
        if not root.channel_slug:
            return None

        return (
            SaleChannelListingBySaleIdAndChanneSlugLoader(info.context)
            .load((root.node.id, root.channel_slug))
            .then(
                lambda channel_listing: channel_listing.currency
                if channel_listing
                else None
            )
        )


class SaleCountableConnection(CountableConnection):
    class Meta:
        node = Sale
