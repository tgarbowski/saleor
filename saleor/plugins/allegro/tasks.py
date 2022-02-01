import logging
from datetime import datetime, timedelta
import math

from ...celeryconf import app
from .api import AllegroAPI
from .enums import AllegroErrors
from .utils import (email_errors, get_plugin_configuration, email_bulk_unpublish_message,
                    get_products_by_recursive_categories, bulk_update_allegro_status_to_unpublished,
                    update_allegro_purchased_error, email_bulk_unpublish_result,
                    get_datetime_now, product_ids_to_skus, get_products_by_channels,
                    AllegroProductPublishValidator, AllegroErrorHandler)
from saleor.plugins.manager import get_plugins_manager
from saleor.product.models import Category, Product, ProductMedia, ProductVariant
from saleor.plugins.allegro import ProductPublishState
from saleor.plugins.models import PluginConfiguration

logger = logging.getLogger(__name__)


@app.task()
def refresh_token_task():
    channels = list(PluginConfiguration.objects.filter(identifier='allegro').values_list(
        'channel__slug', flat=True))

    HOURS_BEFORE_WE_REFRESH_TOKEN = 6

    for channel in channels:
        config = get_plugin_configuration(channel)
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
    allegro_api_instance = AllegroAPI(channel)

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

    product_images = ProductMedia.objects.filter(product=saleor_product)
    product_images = [product_image.image.url for product_image in product_images]

    publication_date = saleor_product.get_value_from_private_metadata("publish.allegro.date")
    # New offer
    if not publication_date:
        product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type, product_images, 'required')
        logger.info('New offer: ' + str(product.get('external').get('id')))
        offer = allegro_api_instance.publish_to_allegro(allegro_product=product)
        description = offer.get('description')

        if offer is None:
            AllegroErrorHandler.update_errors_in_private_metadata(
                saleor_product,
                [error for error in allegro_api_instance.errors],
                channel)

            if products_bulk_ids: email_errors(products_bulk_ids)
            return
        # Assign existing product_id to offer
        existing_product_id = saleor_product.private_metadata.get('publish.allegro.product')
        if existing_product_id:
            allegro_api_instance.add_product_to_offer(
                allegro_product_id=existing_product_id,
                allegro_id=offer.get('id'),
                description=description)
        # Save errors if they exist
        err_handling_response = allegro_api_instance.error_handling(offer, saleor_product)
        # If must_assign_offer_to_product create new product and assign to offer
        if err_handling_response == 'must_assign_offer_to_product' and not existing_product_id:
            offer_id = saleor_product.private_metadata.get('publish.allegro.id')
            parameters = allegro_api_instance.prepare_product_parameters(
                saleor_product,
                'requiredForProduct')
            product = allegro_api_instance.prepare_product(saleor_product, parameters, product['images'])
            product = {"product": product}
            # Propose a new product
            propose_product = allegro_api_instance.propose_a_product(product['product'])
            # If product successfully created
            if propose_product.get('id'):
                saleor_product.store_value_in_private_metadata(
                    {'publish.allegro.product': propose_product['id']})
                saleor_product.save()
                # Update offer with created allegro product ID
                allegro_product = allegro_api_instance.add_product_to_offer(
                    allegro_product_id=propose_product['id'],
                    allegro_id=offer_id,
                    description=description)
                # Save offer-product connection errors
                allegro_api_instance.error_handling_product(allegro_product, saleor_product)
                # Validate final offer
                offer = allegro_api_instance.get_offer(offer_id)
                allegro_api_instance.error_handling(offer, saleor_product)
            else:
                allegro_api_instance.error_handling_product(propose_product, saleor_product)

        if products_bulk_ids:
            email_errors(products_bulk_ids)
        return
    # Update offer
    if publication_date:
        offer_id = saleor_product.private_metadata.get('publish.allegro.id')

        if offer_id:
            product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type,
                                                         product_images, 'required')
            offer_update = allegro_api_instance.update_allegro_offer(allegro_product=product,
                                                                     allegro_id=offer_id)

            description = offer_update.get('description')
            logger.info('Offer update: ' + str(product.get('external').get('id')) + str(offer_update))
            offer = allegro_api_instance.get_offer(offer_id)
            err_handling_response = allegro_api_instance.error_handling(offer, saleor_product)
            # If must_assign_offer_to_product create new product and assign to offer
            if err_handling_response == 'must_assign_offer_to_product':
                parameters = allegro_api_instance.prepare_product_parameters(saleor_product, 'requiredForProduct')
                product = allegro_api_instance.prepare_product(saleor_product, parameters, product['images'])
                product = {"product": product}
                # Propose a new product
                propose_product = allegro_api_instance.propose_a_product(product['product'])
                # If product successfully created
                if propose_product.get('id'):
                    logger.info('Product Created: ' + str(propose_product['id']))
                    saleor_product.store_value_in_private_metadata({'publish.allegro.product': propose_product['id']})
                    saleor_product.save()
                    # Update offer with created allegro product ID
                    allegro_product = allegro_api_instance.add_product_to_offer(
                        allegro_product_id=propose_product['id'],
                        allegro_id=offer_id,
                        description=description)
                    allegro_api_instance.error_handling_product(allegro_product, saleor_product)
                    # Validate final offer
                    offer = allegro_api_instance.get_offer(offer_id)
                    allegro_api_instance.error_handling(offer, saleor_product)
                else:
                    allegro_api_instance.error_handling_product(propose_product, saleor_product)

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
def bulk_allegro_unpublish_buy_now():
    config = get_plugin_configuration()
    allegro_api = AllegroAPI(config['token_value'], config['env'])
    # fetch allegro BUY_NOW from db
    buy_now_products = Category.objects.raw('''
        select id from product_product
        where private_metadata->>'publish.type'='BUY_NOW'
    '''
    )
    products_ids = [product.id for product in buy_now_products]
    skus = list(ProductVariant.objects.filter(product_id__in=products_ids).values_list('sku', flat=True))
    # Unpublish BUY_NOW offers
    total_count = len(skus)
    limit = 1000
    skus_purchased = []
    uuids = []
    for offset in range(0, total_count, limit):
        update_skus = skus[offset:offset + limit]
        allegro_data = allegro_api.bulk_offer_unpublish(skus=update_skus)
        # Skus purchased or errors
        if allegro_data['status'] == 'ERROR':
            skus_purchased.extend(update_skus)
        if allegro_data.get('message') == AllegroErrors.BID_OR_PURCHASED:
            for error in allegro_data["errors"]:
                skus_purchased.append(error['sku'])
        if allegro_data.get('uuid'):
            uuids.append(allegro_data['uuid'])

    unpublished_skus = [sku for sku in skus if sku not in skus_purchased]
    # Set private_metadata allegro.publish.status to 'unpublished' and update date
    bulk_update_allegro_status_to_unpublished(unpublished_skus)
    # Check unpublish status
    if uuids:
        trigger_time = datetime.now() + timedelta(minutes=10)
        for uuid in uuids:
            check_bulk_unpublish_status_task.s(uuid).apply_async(eta=trigger_time)


@app.task()
def bulk_allegro_publish_unpublished_to_auction(limit):
    def calculate_date(i, day_limit):
        # Start from tomorrow with day_limit per day and spread everyday between 7-8 pm
        day = math.ceil((i + 1) / day_limit)
        minute = int(60 * ((i - (day - 1) * day_limit) / day_limit))
        starting_at = now + timedelta(days=day)
        starting_at = starting_at.replace(hour=19, minute=minute)
        return starting_at.strftime("%Y-%m-%d %H:%M")

    config = get_plugin_configuration()
    allegro_api = AllegroAPI(config['token_value'], config['env'])
    manager = get_plugins_manager()
    plugin = manager.get_plugin('allegro')
    # fetch unpublished allegro BUY_NOW offers from db
    # TODO is_publish is no longer a product_product field
    buy_now_products = Category.objects.raw('''
            select id from product_product
            where private_metadata->>'publish.type'='BUY_NOW'
            and private_metadata->>'publish.allegro.status'='unpublished'
            and is_published = false
            limit %s
        ''',[limit]
    )
    instances_ids = [product.id for product in buy_now_products]
    instances = Product.objects.filter(id__in=instances_ids)
    instances_length = len(instances)
    day_limit = 2000
    now = datetime.now()
    # dummy data to pass validation
    dummy_data = {
        "starting_at": "dummy_date",
        "offer_type": "AUCTION"
    }

    for i, instance in enumerate(instances):
        instance.delete_value_from_private_metadata('publish.allegro.date')
        starting_at = calculate_date(i, day_limit)
        products_bulk_ids = instances_ids if i == instances_length - 1 else None
        offer_payload = {
            "product": instance,
            "offer_type": "AUCTION",
            "starting_at": starting_at,
            "products_bulk_ids": products_bulk_ids
        }
        plugin.product_published(offer_payload, None)


@app.task()
def unpublish_from_multiple_channels(product_ids):
    products_per_channels = get_products_by_channels(product_ids)

    for channel in products_per_channels:
        if channel['channel__slug'] == 'allegro':
            bulk_allegro_unpublish(
                channel=channel['channel__slug'],
                product_ids=channel['product_ids']
            )


def bulk_allegro_unpublish(channel, product_ids):
    allegro_api = AllegroAPI(channel=channel)
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
