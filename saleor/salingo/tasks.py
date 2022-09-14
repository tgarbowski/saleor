from datetime import date
import logging

from django.db.models.functions import Substr
from django.db.models import Q
from django.db import connection
from django.conf import settings

from ..celeryconf import app
from saleor.salingo.business_rules import BusinessRulesEvaluator, get_publishable_channel_variants
from saleor.product.models import Product, ProductChannelListing, ProductVariant
from saleor.salingo.sql.raw_sql import duplicated_products
from saleor.salingo.remover import delete_products, remove_background_with_backup
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

    publishable_variants = get_publishable_channel_variants(channel_slug)
    channel_listings = ProductChannelListing.objects.filter(
        product__variants__in=publishable_variants
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
    if settings.APP_ENVIRONMENT == 'production':
        remove_background_with_backup(
            start_date=date_x_days_before(days=7),
            end_date=date.today()
        )
    calculate_prices()
    rotate_channels()

