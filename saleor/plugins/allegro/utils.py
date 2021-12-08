from datetime import datetime
import pytz

from django.core.mail import EmailMultiAlternatives
from django.contrib.postgres.aggregates.general import ArrayAgg
from django.db.models import Q

from saleor.plugins.allegro.enums import AllegroErrors
from saleor.plugins.allegro import ProductPublishState
from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import (Product, ProductVariant, Category, ProductChannelListing,
                                   ProductVariantChannelListing)


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
        manager = get_plugins_manager()
        plugin = manager.get_plugin('allegro')
        plugin.send_mail_with_publish_errors(publish_errors, None)


def get_plugin_configuration(channel):
    manager = get_plugins_manager()
    plugin = manager.get_plugin(
        plugin_id='allegro',
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
        html += '<td style="width: 9rem;">' + str(sku) + '</td>'
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
    products = Category.objects.raw('''
        with recursive categories as (
            select  id, "name", parent_id, "level"
            from product_category
            where slug in %s
            union all
            select pc.id, pc.name, pc.parent_id, pc."level"
            from categories c, product_category pc
            where pc.parent_id = c.id
        )
        select id from product_product pp where category_id in (select id from categories)
        and private_metadata->>'publish.allegro.status'='published'
        order by id
        limit %s
        offset %s
    ''', [category_slugs, limit, offset])

    return products


def bulk_update_allegro_status_to_unpublished(unpublished_skus):
    limit = 1000
    total_count = len(unpublished_skus)
    if total_count > 0:
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

            Product.objects.bulk_update(products_to_update, ['private_metadata'])
            ProductChannelListing.objects.bulk_update(product_channel_listings, ['is_published'])


def update_allegro_purchased_error(skus, allegro_data):
    product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)
    products_to_update = []

    if allegro_data['message'] == AllegroErrors.ALLEGRO_ERROR:
        error_message = allegro_data['errors']
    else:
        error_message = 'Produkt sprzedany lub licytowany'

    for variant in product_variants:
        product = variant.product
        product.store_value_in_private_metadata({'publish.allegro.errors': [error_message]})
        products_to_update.append(product)

    Product.objects.bulk_update(products_to_update, ['private_metadata'])


def product_is_published(product_id):
    published_product = ProductChannelListing.objects.filter(product_id=product_id)

    if not published_product: return True


def get_datetime_now():
    return datetime.now(pytz.timezone('Europe/Warsaw')).strftime('%Y-%m-%d %H:%M:%S')


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


def get_products_by_channels(product_ids):
    # Returns list of dicts of product_ids per channel eg:
    # [{'channel__slug': 'allegro', 'product_ids': [1, 2, 3]}]
    return ProductChannelListing.objects.values('channel__slug').annotate(
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
        self.is_publish_status()
        self.is_allegro_publish_status()

        AllegroErrorHandler.update_errors_in_private_metadata(self.product, self.errors, self.channel)

        return self.errors

    def is_reserved(self):
        if self.product_variant.metadata.get('reserved') is True:
            self.errors.append('003: produkt jest zarezerwowany')

    def is_stock(self):
        if self.product_variant.stocks.first().quantity < 1:
            self.errors.append('002: stan magazynowy produktu wynosi 0')

    def is_location(self):
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
        bundle_id = self.product.private_metadata.get("bundle.id")
        is_bundled = bool(type(bundle_id) is str and len(bundle_id) > 0)
        if is_bundled:
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
            product.store_value_in_private_metadata({'publish.allegro.errors': errors})
        else:
            product_channel_listing.is_published = True
            product.store_value_in_private_metadata({'publish.allegro.errors': []})
        product_channel_listing.save(update_fields=["is_published"])
        product.save(update_fields=["private_metadata"])

    def update_product_errors_in_private_metadata(self, product, errors):
        product.store_value_in_private_metadata({'publish.allegro.errors': errors})
        product.save(update_fields=["private_metadata"])
