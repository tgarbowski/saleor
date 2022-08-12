from datetime import date, datetime, timedelta
import logging

from django.db.models.functions import Substr
from django.db.models import Q
from django.db import connection
from django.conf import settings

from ..celeryconf import app
from saleor.salingo.business_rules import BusinessRulesEvaluator
from saleor.product.models import Product, ProductChannelListing, ProductMedia, ProductVariant
from saleor.salingo.sql.raw_sql import duplicated_products
from saleor.salingo.remover import (RemoverApi, get_media_to_remove, delete_products,
                                    bulk_log_to_oembed_data, BackgroundRemoveStatus)
from saleor.salingo.utils import date_x_days_before, datetime_x_days_before


logger = logging.getLogger(__name__)
workstations = ['00', '01', '02', '03', '04', '05']


@app.task()
def remove_duplicated_products():
    with connection.cursor() as cursor:
        cursor.execute(duplicated_products, (tuple(workstations),))
        rows = cursor.fetchall()

    product_ids = [row[0] for row in rows]
    delete_products(product_ids=product_ids)


@app.task()
def remove_products_without_default_variant():
    products = Product.objects.filter(default_variant__isnull=True)
    product_ids = list(products.values_list("pk", flat=True))
    delete_products(product_ids=product_ids)


@app.task()
def remove_test_products():
    # TODO: find a way to not set product_id
    variants = ProductVariant.objects.annotate(workstation=Substr('sku', 1, 2)).filter(
        ~Q(workstation__in=workstations),
        product_id__gte=1330
    )
    product_ids = list(variants.values_list("product_id", flat=True))
    delete_products(product_ids=product_ids)


@app.task()
def remove_products_with_no_media():
    variants = ProductVariant.objects.annotate(workstation=Substr('sku', 1, 2)).filter(
        workstation__in=workstations,
        product__media__isnull=True,
        product__created__lte=datetime_x_days_before(days=1)
    )

    product_ids = list(variants.values_list("product_id", flat=True))
    delete_products(product_ids=product_ids)


@app.task()
def remove_background(start_date, end_date):
    images = get_media_to_remove(start_date=start_date, end_date=end_date)
    images_paths = [image.image.name for image in images]
    image_ids = [image.id for image in images]

    product_medias = ProductMedia.objects.filter(pk__in=image_ids)

    bulk_log_to_oembed_data(
        product_medias=product_medias,
        status=BackgroundRemoveStatus.PENDING.value
    )

    RemoverApi().process_images_backup_mode(
        source=settings.AWS_MEDIA_BUCKET_NAME,
        target=settings.AWS_MEDIA_BUCKET_NAME,
        backup=settings.AWS_BACKUP_BUCKET_NAME,
        images=images_paths
    )

@app.task()
def rotate_channels():
    routing = BusinessRulesEvaluator(plugin_slug="salingo_routing", mode="commit")
    routing.evaluate_rules()


@app.task()
def calculate_prices():
    pricing = BusinessRulesEvaluator(plugin_slug="salingo_pricing", mode="commit")
    pricing.evaluate_rules()


@app.task()
def publish_local_shop(channel_slug):
    current_date = date.today()

    channel_listings = ProductChannelListing.objects.filter(
        channel__slug=channel_slug,
        is_published=False
    )
    channel_listings.update(
        available_for_purchase=current_date,
        visible_in_listings=True,
        is_published=True,
        publication_date=current_date
    )


def cleanup_products():
    remove_products_with_no_media()
    remove_test_products()
    remove_products_without_default_variant()
    remove_duplicated_products()


@app.task()
def publication_flow():
    cleanup_products()
    remove_background(
        start_date=date_x_days_before(days=7),
        end_date=date.today()
    )
    rotate_channels()
    calculate_prices()
