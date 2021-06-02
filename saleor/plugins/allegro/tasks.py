import logging
from datetime import datetime, timedelta
import pytz

from ...celeryconf import app
from .api import AllegroAPI
from .enums import AllegroErrors
from .utils import email_errors, get_plugin_configuration, email_bulk_unpublish_message
from saleor.product.models import Product
from saleor.plugins.allegro import ProductPublishState

logger = logging.getLogger(__name__)


@app.task()
def refresh_token_task():
    config = get_plugin_configuration()
    token_expiration = config.get('token_access')
    HOURS_BEFORE_WE_REFRESH_TOKEN = 6

    if config['token_access']:
        if AllegroAPI.calculate_hours_to_token_expire(token_expiration) < HOURS_BEFORE_WE_REFRESH_TOKEN:
            access_token, refresh_token, expires_in = AllegroAPI(
                'expiredToken', config['env']).refresh_token(
                    config['refresh_token'],
                    config['client_id'],
                    config['client_secret'],
                    config['saleor_redirect_url'],
                    config['auth_env']) or (None, None, None)
            if access_token and refresh_token and expires_in is not None:
                AllegroAPI.save_token_in_plugin_configuration(access_token, refresh_token, expires_in)


@app.task()
def check_bulk_unpublish_status_task(unique_id):
    config = get_plugin_configuration()
    access_token = config.get('token_value')
    env = config.get('env')
    allegro_api_instance = AllegroAPI(access_token, env)
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
def async_product_publish(product_id, offer_type, starting_at, product_images, products_bulk_ids):
    config = get_plugin_configuration()
    access_token = config.get('token_value')
    env = config.get('env')
    allegro_api_instance = AllegroAPI(access_token, env)
    saleor_product = Product.objects.get(pk=product_id)
    saleor_product.store_value_in_private_metadata(
        {'publish.allegro.status': ProductPublishState.MODERATED.value})
    saleor_product.store_value_in_private_metadata(
        {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw'))
            .strftime('%Y-%m-%d %H:%M:%S')})
    saleor_product.store_value_in_private_metadata({'publish.type': offer_type})
    # New offer
    if saleor_product.get_value_from_private_metadata(
            'publish.allegro.status') == ProductPublishState.MODERATED.value and \
            saleor_product.get_value_from_private_metadata(
                "publish.allegro.date") is None:

        product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type, product_images, 'required')
        logger.info('New offer: ' + str(product.get('external').get('id')))
        offer = allegro_api_instance.publish_to_allegro(allegro_product=product)
        description = offer.get('description')

        if offer is None:
            allegro_api_instance.update_errors_in_private_metadata(
                saleor_product,
                [error for error in allegro_api_instance.errors])

            if products_bulk_ids: email_errors(products_bulk_ids)
            return
        # Save errors if they exist
        err_handling_response = allegro_api_instance.error_handling(offer, saleor_product, ProductPublishState)
        # If must_assign_offer_to_product create new product and assign to offer
        if err_handling_response == 'must_assign_offer_to_product':
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
                offer = allegro_api_instance.valid_offer(offer_id)
                allegro_api_instance.error_handling(offer, saleor_product, ProductPublishState)
            else:
                allegro_api_instance.error_handling_product(propose_product, saleor_product)

        if products_bulk_ids:
            email_errors(products_bulk_ids)
        return
    # Update offer
    if saleor_product.get_value_from_private_metadata('publish.allegro.status') == \
            ProductPublishState.MODERATED.value and \
            saleor_product.get_value_from_private_metadata(
                'publish.allegro.date') is not None:

        offer_id = saleor_product.private_metadata.get('publish.allegro.id')

        if offer_id:
            product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type,
                                                         product_images, 'required')
            offer_update = allegro_api_instance.update_allegro_offer(allegro_product=product,
                                                                     allegro_id=offer_id)

            description = offer_update.get('description')
            logger.info('Offer update: ' + str(product.get('external').get('id')) + str(offer_update))
            offer = allegro_api_instance.valid_offer(offer_id)
            err_handling_response = allegro_api_instance.error_handling(offer, saleor_product, ProductPublishState)
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
                    offer = allegro_api_instance.valid_offer(offer_id)
                    allegro_api_instance.error_handling(offer, saleor_product, ProductPublishState)
                else:
                    allegro_api_instance.error_handling_product(propose_product, saleor_product)

    if products_bulk_ids: email_errors(products_bulk_ids)
