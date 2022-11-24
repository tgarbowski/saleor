from datetime import datetime, timedelta
import math

import graphene

from django.conf import settings
from django.core.exceptions import ValidationError

from saleor.graphql.core.mutations import BaseBulkMutation, BaseMutation
from saleor.plugins.allegro.tasks import publish_products, unpublish_from_multiple_channels
from saleor.graphql.product.filters import ProductFilter, ProductFilterInput
from saleor.salingo.utils import SalingoDatetimeFormats, validate_date_string, validate_datetime_string
from saleor.product.models import ProductChannelListing
from saleor.graphql.product.types import Product, ProductVariant, ProductMedia
from saleor.product import models
from saleor.core.permissions import ProductPermissions
from saleor.graphql.core.types.common import ProductError
from saleor.salingo.images import BackupImageRetrieval


class ProductBulkClearWarehouseLocation(BaseBulkMutation):
    product_variants = graphene.List(
        graphene.NonNull(ProductVariant),
        required=True,
        default_value=[],
        description="List of products with location deleted",
    )

    class Arguments:
        skus = graphene.List(graphene.String, required=True, description="List of products SKUs to remove location")

    class Meta:
        description = "Remove Warehouse Locations"
        model = models.ProductVariant
        object_type = ProductVariant
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"

    @classmethod
    def perform_mutation(cls, _root, info, ids=None, **data):
        product_variants = models.ProductVariant.objects.select_related('product').filter(
            sku__in=data["skus"])
        for product_variant in product_variants:

            product_variant.product.private_metadata["publish.allegro.status"] = "published"
            if "location" in product_variant.private_metadata:
                product_variant.private_metadata["location"] = ""
            product_variant.save()

        return len(product_variants), None

    @classmethod
    def bulk_action(cls, queryset, **kwargs):
        pass


class ProductBulkPublish(BaseBulkMutation):
    class Arguments:
        ids = graphene.List(
            graphene.ID, required=True, description="List of products IDs to publish."
        )
        is_published = graphene.Boolean(
            required=True, description="Determine if products will be published or not."
        )
        offer_type = graphene.String(required=True, description="Determine product offer type.")
        starting_at = graphene.String()
        starting_at_date = graphene.String()
        ending_at_date = graphene.String()
        publish_hour = graphene.String()
        filter = ProductFilterInput()
        channel = graphene.String()
        mode = graphene.String(required=True)

    class Meta:
        description = "Publish products."
        model = models.Product
        object_type = Product
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"

    @classmethod
    def validate_input(cls, data):
        if data.get('mode') == 'PUBLISH_SELECTED':
            validate_datetime_string(data.get('starting_at'), SalingoDatetimeFormats.datetime)
        elif data.get('mode') == 'PUBLISH_ALL':
            if not data.get('filter'):
                raise ValidationError("Filters not provided.")
            validate_date_string(data.get('starting_at_date'), SalingoDatetimeFormats.date)
            cls.parse_time_string(data.get('publish_hour'))

    @classmethod
    def parse_time_string(cls, time_string):
        try:
            hour, minute = time_string.split(':')
            hour, minute = int(hour), int(minute)
        except (AttributeError, ValueError):
            raise ValidationError("Wrong time format.")
        return hour, minute

    @classmethod
    def bulk_action(cls, info, instances, product_ids, **data):
        cls.validate_input(data)
        publish_mode = data['mode']

        if publish_mode == 'PUBLISH_SELECTED':
            product_ids = cls.filter_unpublished_products(product_ids)
            if not product_ids: return
            publish_date = datetime.strptime(data.get('starting_at'), SalingoDatetimeFormats.datetime)
            cls.bulk_publish(product_ids, publish_date, **data)
        elif publish_mode == 'PUBLISH_ALL':
            data['filter']['channel'] = data['channel']
            cls.publish_all(**data)
        elif publish_mode == 'UNPUBLISH_SELECTED':
            cls.bulk_unpublish(product_ids)
        elif publish_mode == 'UNPUBLISH_ALL':
            data['filter']['channel'] = data['channel']
            cls.bulk_unpublish_all(**data)

    @classmethod
    def bulk_unpublish_all(cls, **data):
        product_ids = cls.get_filtered_product_ids(data['filter'])
        unpublish_from_multiple_channels(product_ids=product_ids)

    @classmethod
    def get_filtered_product_ids(cls, filters):
        channel_slug = filters['channel']
        product_ids = ProductChannelListing.objects.filter(channel__slug=channel_slug).values_list(
            'product_id', flat=True
        )

        all_products = models.Product.objects.filter(pk__in=product_ids)
        filtered_products = ProductFilter(
            data=filters, queryset=all_products
        ).qs

        return list(filtered_products.values_list('id', flat=True))

    @classmethod
    def filter_unpublished_products(cls, product_ids):
        channel_listings = ProductChannelListing.objects.filter(
            product_id__in=product_ids,
            is_published=False
        )

        return list(channel_listings.values_list('product_id', flat=True))

    @classmethod
    def publish_all(cls, **data):
        product_ids = cls.get_filtered_product_ids(data['filter'])
        product_ids = cls.filter_unpublished_products(product_ids)
        products_amount = len(product_ids)

        if not product_ids: return

        MAX_OFFERS_DAILY = 1000
        publication_day = 0

        hour, minute = cls.parse_time_string(data.get('publish_hour'))
        starting_at = datetime.strptime(
            data['starting_at_date'],
            SalingoDatetimeFormats.date).replace(hour=hour, minute=minute)

        if data.get('ending_at_date'):
            ending_at = datetime.strptime(
                data['ending_at_date'],
                SalingoDatetimeFormats.date).replace(hour=hour, minute=minute)
            day_diff = ending_at - starting_at
            publication_days = day_diff.days + 1
            amount_per_day = int(min(products_amount / publication_days, MAX_OFFERS_DAILY))
        else:
            amount_per_day = min(products_amount, MAX_OFFERS_DAILY)

        for offset in range(0, products_amount, amount_per_day):
            publish_date = starting_at + timedelta(days=publication_day)
            selected_products = product_ids[offset:offset + amount_per_day]
            cls.bulk_publish(product_ids=selected_products, publish_date=publish_date, **data)
            publication_day += 1

    @classmethod
    def bulk_unpublish(cls, product_ids):
        unpublish_from_multiple_channels(product_ids=product_ids)

    @classmethod
    def bulk_publish(cls, product_ids, publish_date, **data):
        interval = 5
        chunks = 13
        step = math.ceil(len(product_ids) / chunks)
        start = 0
        cls.bulk_set_is_publish_true(product_ids)
        for i, product_id in enumerate(product_ids):
            starting_at = (publish_date + timedelta(minutes=start)).strftime(SalingoDatetimeFormats.datetime)
            products_bulk_ids = product_ids if i == len(product_ids) - 1 else None
            publish_products.apply_async(
                kwargs={
                    'product_id': product_id,
                    'offer_type': data['offer_type'],
                    'starting_at': starting_at,
                    'products_bulk_ids': products_bulk_ids,
                    'channel': data['channel']
                },
                queue=settings.CELERY_LONG_TASKS_QUEUE
            )

            if (i + 1) % step == 0:
                start += interval

    @classmethod
    def bulk_set_is_publish_true(cls, product_ids):
        products_amount = len(product_ids)
        limit = 1000

        for offset in range(0, products_amount, limit):
            ProductChannelListing.objects.filter(
                product_id__in=product_ids[offset:offset + limit]
            ).update(is_published=True)


class ProductMediaRetrieveFromBackup(BaseMutation):
    media = graphene.Field(ProductMedia)
    product = graphene.Field(Product)

    class Arguments:
        id = graphene.ID(required=True, description="ID of a product media to delete.")

    class Meta:
        description = "Retrieves a product media from backup."
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError
        error_type_field = "product_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        media_obj = cls.get_node_or_error(info, data.get("id"), only_type=ProductMedia)

        if media_obj:
            backup_image_retrieval = BackupImageRetrieval(image=str(media_obj.image))
            backup_image_retrieval.handle()

        return ProductMediaRetrieveFromBackup(media=media_obj)
