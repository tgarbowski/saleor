import logging
from datetime import datetime, timedelta

from ...celeryconf import app
from .api import AllegroAPI
from .enums import AllegroErrors
from .utils import (email_errors, get_plugin_configuration, email_bulk_unpublish_message,
                    get_products_by_recursive_categories, bulk_update_allegro_status_to_unpublished,
                    update_allegro_purchased_error, email_bulk_unpublish_result,
                    get_datetime_now, product_ids_to_skus, get_products_by_channels,
                    AllegroProductPublishValidator, AllegroErrorHandler,
                    get_product_media_urls, get_allegro_channels_slugs, get_specified_allegro_channels_slugs,
                    returned_products)
from saleor.product.models import Product
from saleor.plugins.allegro import ProductPublishState
from .orders import cancel_allegro_orders, insert_allegro_orders
from saleor.order.models import Fulfillment


logger = logging.getLogger(__name__)


@app.task()
def refresh_token_task():
    channels = get_allegro_channels_slugs()

    HOURS_BEFORE_WE_REFRESH_TOKEN = 6

    for channel in channels:
        config = get_plugin_configuration(plugin_id='allegro', channel=channel)
        token_expiration = config.get('token_access')

        if config['token_access']:
            if AllegroAPI.calculate_hours_to_token_expire(token_expiration) < HOURS_BEFORE_WE_REFRESH_TOKEN:
                allegro_api = AllegroAPI(channel=channel)
                access_token, refresh_token, expires_in = allegro_api.refresh_token() or (None, None, None)
                if access_token and refresh_token and expires_in is not None:
                    allegro_api.save_token_in_plugin_configuration(access_token, refresh_token, expires_in)


@app.task()
def check_bulk_unpublish_status_task(unique_id):
    allegro_api_instance = AllegroAPI(channel='allegro')
    unpublish_status = allegro_api_instance.check_unpublish_status(unique_id)

    if unpublish_status.get('status') == 'OK':
        email_bulk_unpublish_message('OK')
    if unpublish_status.get('status') == 'PROCEEDING':
        trigger_time = datetime.now() + timedelta(minutes=10)
        check_bulk_unpublish_status_task.s(unique_id).apply_async(eta=trigger_time)
    if unpublish_status.get('status') == 'ERROR':
        if unpublish_status.get('message') == AllegroErrors.TASK_FAILED:
            email_bulk_unpublish_message('ERROR', message=AllegroErrors.TASK_FAILED,
                                         errors=unpublish_status.get('errors'))
        else:
            email_bulk_unpublish_message('ERROR', errors=unpublish_status)


@app.task()
def publish_products(product_id, offer_type, starting_at, products_bulk_ids, channel):
    allegro_api = AllegroAPI(channel)

    saleor_product = Product.objects.get(pk=product_id)
    saleor_product.delete_value_from_private_metadata('publish.allegro.errors')
    saleor_product.save()

    validator = AllegroProductPublishValidator(product=saleor_product, channel=channel)

    if validator.validate():
        saleor_product.store_value_in_private_metadata(
            {'publish.allegro.status': ProductPublishState.MODERATED.value,
             'publish.status.date': get_datetime_now()})
        saleor_product.save(update_fields=["private_metadata"])
        return

    saleor_product.store_value_in_private_metadata(
        {'publish.allegro.status': ProductPublishState.MODERATED.value,
         'publish.type': offer_type,
         'publish.status.date': get_datetime_now()})
    saleor_product.save()

    product_images = get_product_media_urls(product=saleor_product)
    publication_date = saleor_product.get_value_from_private_metadata("publish.allegro.date")
    existing_product_id = saleor_product.private_metadata.get('publish.allegro.product')
    # New offer
    if not publication_date:
        product = allegro_api.prepare_offer(saleor_product, starting_at, offer_type, product_images, 'required')
        logger.info('New offer: ' + str(product.get('external').get('id')))
        offer = allegro_api.publish_to_allegro(allegro_product=product)
        description = offer.get('description')

        if offer is None:
            AllegroErrorHandler.update_errors_in_private_metadata(
                saleor_product,
                [error for error in allegro_api.errors],
                channel)

            if products_bulk_ids: email_errors(products_bulk_ids)
            return
        # Save errors if they exist
        err_handling_response = allegro_api.error_handling(offer, saleor_product)
        # If must_assign_offer_to_product create new product and assign to offer
        # OR Assign existing product_id to offer
        if err_handling_response == 'must_assign_offer_to_product' and existing_product_id:
            allegro_product = allegro_api.add_product_to_offer(
                allegro_product_id=existing_product_id,
                allegro_id=offer.get('id'),
                description=description)
            allegro_api.error_handling_product(allegro_product, saleor_product)
            # Validate final offer
            offer = allegro_api.get_offer(offer.get('id'))
            allegro_api.error_handling(offer, saleor_product)
        elif err_handling_response == 'must_assign_offer_to_product' and not existing_product_id:
            offer_id = saleor_product.private_metadata.get('publish.allegro.id')
            parameters = allegro_api.prepare_product_parameters(
                saleor_product,
                'requiredForProduct')
            product = allegro_api.prepare_product(saleor_product, parameters, product['images'])
            product = {"product": product}
            # Propose a new product
            propose_product = allegro_api.propose_a_product(product['product'])
            # If product successfully created
            if propose_product.get('id'):
                saleor_product.store_value_in_private_metadata(
                    {'publish.allegro.product': propose_product['id']})
                saleor_product.save()
                # Update offer with created allegro product ID
                allegro_product = allegro_api.add_product_to_offer(
                    allegro_product_id=propose_product['id'],
                    allegro_id=offer_id,
                    description=description)
                # Save offer-product connection errors
                allegro_api.error_handling_product(allegro_product, saleor_product)
                # Validate final offer
                offer = allegro_api.get_offer(offer_id)
                allegro_api.error_handling(offer, saleor_product)
            else:
                allegro_api.error_handling_product(propose_product, saleor_product)

        if products_bulk_ids:
            email_errors(products_bulk_ids)
        return
    # Update offer
    offer_id = saleor_product.private_metadata.get('publish.allegro.id')
    if publication_date and offer_id:
        product = allegro_api.prepare_offer(saleor_product, starting_at, offer_type,
                                            product_images, 'required')
        offer_update = allegro_api.update_allegro_offer(allegro_product=product,
                                                        allegro_id=offer_id)

        description = offer_update.get('description')
        logger.info('Offer update: ' + str(product.get('external').get('id')) + str(offer_update))
        offer = allegro_api.get_offer(offer_id)
        err_handling_response = allegro_api.error_handling(offer, saleor_product)
        # If must_assign_offer_to_product create new product and assign to offer
        # OR Assign existing product_id to offer
        if err_handling_response == 'must_assign_offer_to_product' and existing_product_id:
            allegro_product = allegro_api.add_product_to_offer(
                allegro_product_id=existing_product_id,
                allegro_id=offer.get('id'),
                description=description)
            allegro_api.error_handling_product(allegro_product, saleor_product)
            # Validate final offer
            offer = allegro_api.get_offer(offer_id)
            allegro_api.error_handling(offer, saleor_product)
        elif err_handling_response == 'must_assign_offer_to_product' and not existing_product_id:
            parameters = allegro_api.prepare_product_parameters(saleor_product, 'requiredForProduct')
            product = allegro_api.prepare_product(saleor_product, parameters, product['images'])
            product = {"product": product}
            # Propose a new product
            propose_product = allegro_api.propose_a_product(product['product'])
            # If product successfully created
            if propose_product.get('id'):
                logger.info('Product Created: ' + str(propose_product['id']))
                saleor_product.store_value_in_private_metadata({'publish.allegro.product': propose_product['id']})
                saleor_product.save()
                # Update offer with created allegro product ID
                allegro_product = allegro_api.add_product_to_offer(
                    allegro_product_id=propose_product['id'],
                    allegro_id=offer_id,
                    description=description)
                allegro_api.error_handling_product(allegro_product, saleor_product)
                # Validate final offer
                offer = allegro_api.get_offer(offer_id)
                allegro_api.error_handling(offer, saleor_product)
            else:
                allegro_api.error_handling_product(propose_product, saleor_product)

    if products_bulk_ids: email_errors(products_bulk_ids)


@app.task()
def update_published_offers_parameters(category_slugs, limit, offset):
    config = get_plugin_configuration()
    allegro_api = AllegroAPI(config['token_value'], config['env'])
    category_slugs = category_slugs.split(',')

    if len(category_slugs) == 1:
        category_slugs = (category_slugs[0],)
    else:
        category_slugs = tuple(category_slugs)

    all_products = get_products_by_recursive_categories(category_slugs, None, 0)
    all_products_amount = len(all_products)

    products = get_products_by_recursive_categories(category_slugs, limit, offset)
    products_ids = []

    for product in products:
        products_ids.append(product.id)

    products = Product.objects.select_related('product_type').filter(id__in=products_ids)
    allowed_statuses = ['ACTIVE', 'ACTIVATING']

    for count, product in enumerate(products):
        logger.info(f'Product {count + 1}/{limit}/{all_products_amount}')
        offer_id = product.private_metadata.get('publish.allegro.id')
        if offer_id:
            allegro_offer = allegro_api.get_offer(offer_id)
            try:
                allegro_status = allegro_offer.get('publication').get('status')
            except AttributeError:
                logger.info(f'No offer found for product {product.id}')
                continue
            if allegro_offer.get('errors') is None and allegro_status in allowed_statuses:
                parameters = allegro_api.prepare_product_parameters(product, 'required')
                allegro_offer['parameters'] = parameters
                offer_update = allegro_api.update_allegro_offer(
                    allegro_product=allegro_offer,
                    allegro_id=offer_id
                )
                if offer_update.get('errors'):
                    logger.info(f'Offer parameters update errors: {offer_update["errors"]}')
            else:
                logger.info(f'No offer found or offer not active/draft for product {product.id}')
        else:
            logger.info(f'publish.allegro.id is empty for product {product.id}')


@app.task()
def unpublish_from_multiple_channels(product_ids):
    products_per_channels = get_products_by_channels(
        product_ids=product_ids,
        channel_slugs=get_allegro_channels_slugs()
    )

    for channel in products_per_channels:
        if channel['product_ids']:
            bulk_allegro_unpublish(
                channel=channel['channel__slug'],
                product_ids=channel['product_ids']
            )


def bulk_allegro_unpublish(channel, product_ids):
    allegro_api = AllegroAPI(channel=channel)
    returned_product_ids = returned_products(product_ids)
    product_ids = [product_id for product_id in product_ids if product_id not in returned_product_ids]
    skus = product_ids_to_skus(product_ids)
    logger.info(f'SKUS TO UNPUBLISH{skus}')

    total_count = len(skus)
    limit = 1000
    skus_purchased = []

    for offset in range(0, total_count, limit):
        update_skus = skus[offset:offset + limit]
        allegro_data = allegro_api.bulk_offer_unpublish(skus=update_skus)
        logger.info(f'BULK OFFER UNPUBLISH RETURN DATA{allegro_data}')
        if allegro_data['status'] == 'ERROR':
            skus_purchased.extend(update_skus)
        if allegro_data['status'] == "OK" and allegro_data['errors']:
            for error in allegro_data["errors"]:
                skus_purchased.append(error['sku'])

    unpublished_skus = [sku for sku in skus if sku not in skus_purchased]
    logger.info(f'UNPUBSLISHED SKUS{unpublished_skus}')
    # Set private_metadata allegro.publish.status to 'unpublished' and update date
    bulk_update_allegro_status_to_unpublished(unpublished_skus)
    # Log error in private metadata if purchased/bid/connection error
    logger.info(f'SKUS PURCHASED{skus_purchased}')
    if skus_purchased:
        update_allegro_purchased_error(skus_purchased, allegro_data)
    # Send unpublished to email
    email_bulk_unpublish_result(skus_purchased)

    return skus_purchased


@app.task()
def save_allegro_orders_task(channels_datetime):
    slugs = list(channels_datetime.keys())
    channels = get_specified_allegro_channels_slugs(channel_slugs=slugs)

    for channel in channels:
        datetime_from = channels_datetime[channel]
        insert_allegro_orders(channel_slug=channel, datetime_from=datetime_from)


@app.task()
def cancel_allegro_orders_task(channels_datetime):
    slugs = list(channels_datetime.keys())
    channels = get_specified_allegro_channels_slugs(channel_slugs=slugs)

    for channel in channels:
        datetime_from = channels_datetime[channel]
        cancel_allegro_orders(channel_slug=channel, datetime_from=datetime_from)


def change_allegro_order_status(order, status):
    allegro_order_id = order.get_value_from_metadata("allegro_order_id")
    api = AllegroAPI(channel=order.channel.slug)
    api.update_order_status(order_id=allegro_order_id, status=status)


def update_allegro_tracking_number(order):
    fulfillment = Fulfillment.objects.filter(order=order).exclude(
        tracking_number__exact=''
    ).first()

    tracking_number = fulfillment.tracking_number
    allegro_order_id = order.get_value_from_metadata("allegro_order_id")
    shipping_method = order.shipping_method
    allegro_shipping_method_id = shipping_method.get_value_from_metadata("allegro_id")

    api = AllegroAPI(channel=order.channel.slug)
    api.add_parcel_tracking_number(
        order_id=allegro_order_id,
        carrier_id=allegro_shipping_method_id,
        waybill=tracking_number
    )
