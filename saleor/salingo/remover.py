from enum import Enum
import logging

import requests

from django.conf import settings

from saleor.product.models import ProductMedia
from saleor.salingo.sql.raw_sql import products_media_to_remove_background
from saleor.graphql.product.bulk_mutations.products import ProductBulkDelete
from saleor.graphql.product.utils import get_draft_order_lines_data_for_variants
from saleor.order.models import OrderLine
from saleor.order.tasks import recalculate_orders_task
from saleor.product.models import Product, ProductVariant


logger = logging.getLogger(__name__)


class BackgroundRemoveStatus(Enum):
    PENDING = 'PENDING'
    FAILURE = 'FAILURE'
    SUCCESS = 'SUCCESS'


class RemoverApi:
    @staticmethod
    def process_images_migration_mode(source, target, images):
        url = f'{settings.REMOVER_API_URL}/process_images/migration'
        headers = {
            "X-API-KEY": settings.REMOVER_API_KEY
        }
        data = {
            "source": source,
            "target": target,
            "images": images
        }

        response = requests.post(
            url=url,
            json=data,
            headers=headers
        )
        return response

    @staticmethod
    def process_images_backup_mode(source, target, backup, images):
        url = f'{settings.REMOVER_API_URL}/process_images/backup'
        headers = {
            "X-API-KEY": settings.REMOVER_API_KEY
        }
        data = {
            "source": source,
            "target": target,
            "backup": backup,
            "images": images
        }

        response = requests.post(
            url=url,
            json=data,
            headers=headers
        )
        return response


def get_media_to_remove(start_date, end_date):
    images = ProductMedia.objects.raw(
        products_media_to_remove_background,
        [start_date, end_date]
    )

    return images


def bulk_log_to_oembed_data(product_medias, status):
    for product_media in product_medias:
        product_media.oembed_data['background_remove_status'] = status

    ProductMedia.objects.bulk_update(
        objs=product_medias,
        fields=['oembed_data'],
        batch_size=100
    )


def bulk_sign_images_by_url(media_urls):
    medias = ProductMedia.objects.filter(image__in=media_urls)
    bulk_log_to_oembed_data(
        product_medias=medias,
        status=BackgroundRemoveStatus.SUCCESS.value
    )


def product_ids_to_variant_ids(product_ids):
    variants = ProductVariant.objects.filter(product_id__in=product_ids)
    variant_ids = list(variants.values_list("pk", flat=True))
    return variant_ids


def delete_products(product_ids):
    # Remove attributes
    ProductBulkDelete.delete_assigned_attribute_values(instance_pks=product_ids)

    # Remove draft order lines data
    draft_order_lines_data = get_draft_order_lines_data_for_variants(
        variant_ids=product_ids_to_variant_ids(product_ids)
    )

    # Delete products
    Product.objects.filter(pk__in=product_ids).delete()

    # delete order lines for deleted variants
    OrderLine.objects.filter(
        pk__in=draft_order_lines_data.line_pks
    ).delete()

    order_pks = draft_order_lines_data.order_pks
    if order_pks:
        recalculate_orders_task.delay(list(order_pks))


def remove_background_with_backup(start_date, end_date):
    images = get_media_to_remove(start_date=start_date, end_date=end_date)
    images_paths = [image.image.name for image in images]
    image_ids = [image.id for image in images]

    product_medias = ProductMedia.objects.filter(pk__in=image_ids)

    bulk_log_to_oembed_data(
        product_medias=product_medias,
        status=BackgroundRemoveStatus.PENDING.value
    )

    remover_response = RemoverApi().process_images_backup_mode(
        source=settings.AWS_MEDIA_BUCKET_NAME,
        target=settings.AWS_MEDIA_BUCKET_NAME,
        backup=settings.AWS_BACKUP_BUCKET_NAME,
        images=images_paths
    )

    logger.info(remover_response.json())
