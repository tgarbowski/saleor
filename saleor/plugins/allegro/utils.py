from datetime import datetime
import pytz

from django.core.mail import EmailMultiAlternatives

from saleor.plugins.allegro.enums import AllegroErrors
from saleor.plugins.allegro import ProductPublishState
from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import Product, ProductVariant, Category, ProductChannelListing


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


def get_plugin_configuration():
    manager = get_plugins_manager()
    plugin = manager.get_plugin('allegro', 'allegro')
    configuration = {item["name"]: item["value"] for item in plugin.configuration}
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
                sku__in=update_skus)
            products_to_update = []
            for variant in product_variants:
                product = variant.product
                product.is_published = False
                product.store_value_in_private_metadata(
                    {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw'))
                        .strftime('%Y-%m-%d %H:%M:%S')})
                product.store_value_in_private_metadata(
                    {'publish.allegro.status': ProductPublishState.MODERATED.value})
                products_to_update.append(product)
            Product.objects.bulk_update(products_to_update, ['private_metadata', 'is_published'])


def can_publish(instance, data):
    can_be_published = False

    is_bundled = False
    bundle_id = instance.private_metadata.get("bundle.id")
    is_bundled = bool(type(bundle_id) is str and len(bundle_id) > 0)

    publish_status_verify = bool(
        instance.private_metadata.get('publish.allegro.status') not in [
            ProductPublishState.SOLD.value,
            ProductPublishState.PUBLISHED.value
        ]
    )

    if (    not product_is_published(instance.id)
        and data.get('starting_at')
        and data.get('offer_type')
        and publish_status_verify
        and not is_bundled
    ):
        can_be_published = True

    return True

    return can_be_published


def update_allegro_purchased_error(skus):
    product_variants = ProductVariant.objects.select_related('product').filter(sku__in=skus)
    products_to_update = []

    for variant in product_variants:
        product = variant.product
        product.store_value_in_private_metadata(
            {'publish.allegro.errors': ["Wycofanie produktu zakończone niepowodzeniem"]})
        products_to_update.append(product)

    Product.objects.bulk_update(products_to_update, ['private_metadata'])


def product_is_published(product_id):
    published_product = ProductChannelListing.objects.filter(product_id=product_id)

    if not published_product: return True
