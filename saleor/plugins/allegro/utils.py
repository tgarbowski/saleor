from datetime import datetime
import pytz
from typing import List

from dateutil import parser

from django.core.mail import EmailMultiAlternatives
from django.contrib.postgres.aggregates.general import ArrayAgg
from django.db.models import Q

from saleor.plugins.allegro.enums import AllegroErrors
from saleor.plugins.allegro import ProductPublishState
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from saleor.product.models import (Product, ProductVariant, Category, ProductChannelListing,
                                   ProductVariantChannelListing, ProductMedia)
from saleor.salingo.utils import SalingoDatetimeFormats
from saleor.salingo.sql.raw_sql import products_by_recursive_categories


def email_errors(products_bulk_ids):
    # Send email on last bulk item
    products = Product.objects.filter(id__in=products_bulk_ids)
    publish_errors = []

    for product in products:
        error = product.get_value_from_private_metadata('publish.allegro.errors')
        if error is not None:
            publish_errors.append(
                {'sku': product.variants.first().sku, 'errors': error})

    if publish_errors:
        send_mail_with_publish_errors(publish_errors)


def send_mail_with_publish_errors(publish_errors):
    subject = 'Logi z wystawiania ofert'
    from_email = 'noreply.salingo@gmail.com'
    to = 'noreply.salingo@gmail.com'
    text_content = 'Logi z wystawiania ofert:'
    html_content = create_table(publish_errors)
    message = EmailMultiAlternatives(subject, text_content, from_email, [to])
    message.attach_alternative(html_content, "text/html")
    return message.send()


def create_table(errors):
    html = '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '<th></th>'
    html += '</tr>'
    for error in errors:
        html += '<tr>'
        try:
            if len(error.get('errors')) > 0:
                html += '<td style="width: 9rem;">' + str(error.get('sku')) + '</td>'
                html += '<td>' + str(error.get('errors')) + '</td>'
        except:
            if len(error) > 0:
                html += '<td>' + str(error) + '</td>'
        html += '</tr>'
    html += '<tr>'
    html += '<td>' + '</td>'
    html += '</tr>'
    html += '</table>'
    html += '<br>'
    html += '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    #html += '<td>' + 'Poprawnie przetworzone: ' + str(len([error for error in errors if len(error.get('errors')) == 0])) + '</td>'
    html += '</tr>'
    html += '<tr>'
    #html += '<td>' + 'Niepropawnie przetworzone: ' + str(len([error for error in errors if len(error.get('errors')) > 0])) + '</td>'
    html += '</tr>'
    html += '</table>'

    return html


def get_plugin_configuration(plugin_id, channel=None):
    manager = get_plugins_manager()
    plugin = manager.get_plugin(
        plugin_id=plugin_id,
        channel_slug=channel)
    configuration = {item["name"]: item["value"] for item in plugin.configuration if plugin.configuration}
    return configuration


def email_bulk_unpublish_message(status, **kwargs):
    if status == 'OK':
        message = 'Wszystkie oferty dla danych SKU zostały pomyślnie wycofane'
    elif status == 'ERROR':
        if kwargs.get('message') == AllegroErrors.TASK_FAILED:
            message = prepare_failed_tasks_email(kwargs.get('errors'))
        else:
            message = str(kwargs.get('errors'))

    send_mail(message)


def email_bulk_unpublish_result(failed_skus):
    if not failed_skus:
        message = 'Wszystkie oferty dla danych SKU zostały pomyślnie wycofane.'
    else:
        message = prepare_failed_tasks_email(failed_skus)

    send_mail(message)


def send_mail(message):
    subject = 'Logi z wycofywania ofert'
    from_email = 'noreply.salingo@gmail.com'
    to = 'noreply.salingo@gmail.com'
    text_content = 'Logi z wycofywania ofert:'
    html_content = message
    message = EmailMultiAlternatives(subject, text_content, from_email, [to])
    message.attach_alternative(html_content, "text/html")
    return message.send()


def prepare_failed_tasks_email(skus):
    html = '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '<th>Nie udało się wycofać poniższych SKU</th>'
    html += '</tr>'
    for sku in skus:
        html += '<tr>'
        html += '<td style="width: 9rem;">' + f'SKU: {sku["sku"]}, REASON: {sku["reason"]}' + '</td>'
        html += '</tr>'
    html += '<tr>'
    html += '<td>' + '</td>'
    html += '</tr>'
    html += '</table>'
    html += '<br>'
    html += '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '</tr>'
    html += '<tr>'
    html += '</tr>'
    html += '</table>'

    return html


def get_products_by_recursive_categories(category_slugs, limit, offset):
    return Category.objects.raw(products_by_recursive_categories, [category_slugs, limit, offset])


def bulk_update_allegro_status_to_unpublished(unpublished_skus):
    limit = 1000
    total_count = len(unpublished_skus)

    for offset in range(0, total_count, limit):
        update_skus = unpublished_skus[offset:offset + limit]
        product_variants = ProductVariant.objects.select_related('product').filter(
            sku__in=update_skus).exclude(product__private_metadata__contains={"publish.allegro.status": "sold"})
        products_to_update = []
        for variant in product_variants:
            product = variant.product
            status_date = datetime.now(pytz.timezone('Europe/Warsaw')).strftime('%Y-%m-%d %H:%M:%S')
            product.store_value_in_private_metadata(
                {'publish.status.date': status_date,
                 'publish.allegro.status': ProductPublishState.MODERATED.value,
                 'publish.allegro.errors': []
                })
            products_to_update.append(product)

        product_channel_listings = ProductChannelListing.objects.filter(
            product__in=products_to_update)
        for listing in product_channel_listings:
            listing.is_published = False

        Product.objects.bulk_update(products_to_update, ['private_metadata'], batch_size=100)
        ProductChannelListing.objects.bulk_update(product_channel_listings, ['is_published'], batch_size=500)


def update_allegro_purchased_error(skus_purchased):
    all_skus = [sku['sku'] for sku in skus_purchased]
    sku_error_map = {}
    for err in skus_purchased:
        sku_error_map[err['sku']] = err['reason']

    variants = ProductVariant.objects.filter(sku__in=all_skus).select_related('product')
    products = []

    for variant in variants:
        error_message = f'Status wycofania: {sku_error_map[variant.sku]}'
        variant.product.store_value_in_private_metadata(
            {
                'publish.allegro.errors': [error_message],
                'allegro_unpublish_action': True
            }
        )
        products.append(variant.product)

    Product.objects.bulk_update(products, ['private_metadata'])


def product_is_published(product_id):
    published_product = ProductChannelListing.objects.filter(product_id=product_id)

    if not published_product: return True


def get_datetime_now():
    return datetime.now(pytz.timezone('Europe/Warsaw')).strftime(
        SalingoDatetimeFormats.datetime_with_seconds)


def get_date_now():
    return datetime.now(pytz.timezone('Europe/Warsaw')).strftime(
        SalingoDatetimeFormats.date)


def format_allegro_datetime(allegro_datetime: str) -> str:
    return parser.parse(allegro_datetime).strftime(SalingoDatetimeFormats.datetime_with_seconds)


def product_ids_to_skus(product_ids):
    return list(
        ProductVariant.objects
            .filter(product_id__in=product_ids)
            .values_list("sku", flat=True)
    )


def skus_to_product_ids(skus):
    return list(
        ProductVariant.objects
            .filter(sku__in=skus)
            .values_list("product_id", flat=True)
    )


def get_products_by_channels(product_ids, channel_slugs):
    # Returns list of dicts of product_ids per channel eg:
    # [{'channel__slug': 'allegro', 'product_ids': [1, 2, 3]}]
    return ProductChannelListing.objects.filter(channel__slug__in=channel_slugs).values('channel__slug').annotate(
        product_ids=ArrayAgg(
            'product_id',
            filter=Q(product_id__in=product_ids)
        )
    ).order_by('channel__slug')


class AllegroProductPublishValidator:
    def __init__(self, product, channel):
        self.product = product
        self.product_channel_listing = ProductChannelListing.objects.get(product=product)
        self.product_variant = product.variants.first()
        self.product_variant_channel_listing = ProductVariantChannelListing.objects.get(
            variant=self.product_variant)
        self.channel = channel
        self.errors = []

    def validate(self):
        self.is_reserved()
        self.is_stock()
        self.is_location()
        self.is_price_amount()
        self.is_cost_price_amount()
        self.is_bundled()
        self.is_allegro_publish_status()
        self.is_allegro_price()

        AllegroErrorHandler.update_errors_in_private_metadata(self.product, self.errors, self.channel)

        return self.errors

    def is_reserved(self):
        if self.product_variant.metadata.get('reserved') is True:
            self.errors.append('003: produkt jest zarezerwowany')

    def is_stock(self):
        if self.product_variant.stocks.first().quantity < 1:
            self.errors.append('002: stan magazynowy produktu wynosi 0')

    def is_location(self):
        if self.product.product_type.name == 'Mega Paka':
            return

        if self.product_variant.private_metadata.get('location') is None:
            self.errors.append('003: brak lokacji magazynowej dla produktu')

    def is_price_amount(self):
        if self.product_variant_channel_listing.price_amount == 0:
            self.errors.append('003: cena produktu wynosi 0')

    def is_cost_price_amount(self):
        if self.product_variant_channel_listing.cost_price_amount == 0 \
                or self.product_variant_channel_listing.cost_price_amount is None:
            self.errors.append('003: cena zakupowa produktu wynosi 0')

    def is_bundled(self):
        if self.product.get_value_from_private_metadata("bundle.id"):
            self.errors.append('003: produkt zbundlowany')

    def is_publish_status(self):
        if self.product_channel_listing.is_published is True:
            self.errors.append('003: produkt w statusie publish')

    def is_allegro_publish_status(self):
        publish_status_verify = bool(
            self.product.private_metadata.get('publish.allegro.status') not in [
                ProductPublishState.SOLD.value,
                ProductPublishState.PUBLISHED.value
            ]
        )

        if publish_status_verify is False:
            self.errors.append('003: błędny status publikacji')

    def is_allegro_price(self):
        if self.product.get_value_from_private_metadata('publish.allegro.price'):
            self.errors.append('003: publish.allegro.price still exists')


class AllegroErrorHandler:

    @staticmethod
    def update_status_and_publish_data_in_private_metadata(product, allegro_offer_id, status,
                                                           errors, channel):
        product.store_value_in_private_metadata(
            {'publish.allegro.status': status,
             'publish.allegro.date': get_datetime_now(),
             'publish.status.date': get_datetime_now(),
             'publish.allegro.id': str(allegro_offer_id)})
        AllegroErrorHandler.update_errors_in_private_metadata(product, errors, channel)
        product.save()

    @staticmethod
    def update_errors_in_private_metadata(product, errors, channel):
        product_channel_listing = ProductChannelListing.objects.get(
            channel__slug=channel,
            product=product)

        if errors:
            product_channel_listing.is_published = False
            product_channel_listing.publication_date = None
            product_channel_listing.available_for_purchase = None
            product_channel_listing.visible_in_listings = False
            product.store_value_in_private_metadata({'publish.allegro.errors': errors})
        else:
            product_channel_listing.is_published = True
            product_channel_listing.publication_date = get_date_now()
            product_channel_listing.available_for_purchase = get_date_now()
            product_channel_listing.visible_in_listings = True
            product.store_value_in_private_metadata({'publish.allegro.errors': []})
        product_channel_listing.save()
        product.save(update_fields=["private_metadata"])

    @staticmethod
    def update_product_errors_in_private_metadata(product, errors):
        product.store_value_in_private_metadata({'publish.allegro.errors': errors})
        product.save(update_fields=["private_metadata"])


def get_product_media_urls(product: "Product") -> [str]:
    product_medias = ProductMedia.objects.filter(product=product)
    return [product_media.image.url for product_media in product_medias]


def get_allegro_channels_slugs() -> [str]:
    channels = PluginConfiguration.objects.filter(
        identifier='allegro',
        active=True
    ).values_list('channel__slug', flat=True)

    return list(channels)


def get_specified_allegro_channels_slugs(channel_slugs: List[str]) -> [str]:
    channels = PluginConfiguration.objects.filter(
        identifier='allegro',
        active=True,
        channel__slug__in=channel_slugs
    ).values_list('channel__slug', flat=True)

    return list(channels)


def returned_products(product_ids) -> List[str]:
    returned_product_ids = []
    products = Product.objects.filter(pk__in=product_ids)

    for product in products:
        if (
                product.get_value_from_private_metadata('publish.allegro.status') == 'moderated'
                and product.get_value_from_private_metadata('publish.allegro.price')
        ):
            returned_product_ids.append(product.pk)

    return returned_product_ids


def get_unpublishable_skus(product_ids):
    returned_product_ids = returned_products(product_ids)
    product_ids = [product_id for product_id in product_ids if product_id not in returned_product_ids]
    return product_ids_to_skus(product_ids)


def filter_out_missing_skus(skus):
    return list(ProductVariant.objects.filter(sku__in=skus).values_list('sku', flat=True))
