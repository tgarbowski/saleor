from django.core.mail import EmailMultiAlternatives

from saleor.plugins.allegro.enums import AllegroErrors
from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import Product


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
    plugin = manager.get_plugin('allegro')
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


def send_mail(message):
    subject = 'Logi z wycofywania ofert'
    from_email = 'noreply.salingo@gmail.com'
    to = 'noreply.salingo@gmail.com'
    text_content = 'Logi z wycofywania ofert:'
    html_content = message
    message = EmailMultiAlternatives(subject, text_content, from_email, [to])
    message.attach_alternative(html_content, "text/html")
    return message.send()


def prepare_failed_tasks_email(errors):
    html = '<table style="width:100%; margin-bottom: 1rem;">'
    html += '<tr>'
    html += '<th></th>'
    html += '</tr>'
    for error in errors:
        html += '<tr>'
        html += '<td style="width: 9rem;">' + str(error.get('offer').get('id')) + '</td>'
        html += '<td>' + 'errors: ' + str(error.get('errors')) + '</td>'
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
