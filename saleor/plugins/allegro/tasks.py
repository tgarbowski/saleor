import logging
from datetime import datetime
import pytz

from ...celeryconf import app
from .utils import AllegroAPI, email_errors
from saleor.product.models import Product
from saleor.plugins.allegro import ProductPublishState

logger = logging.getLogger(__name__)


@app.task
def async_product_publish(token_allegro, env_allegro, product_id, offer_type, starting_at, product_images, products_bulk_ids, is_published):
    allegro_api_instance = AllegroAPI(token_allegro, env_allegro)

    saleor_product = Product.objects.get(pk=product_id)
    saleor_product.store_value_in_private_metadata(
        {'publish.allegro.status': ProductPublishState.MODERATED.value})
    saleor_product.store_value_in_private_metadata(
        {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw'))
            .strftime('%Y-%m-%d %H:%M:%S')})
    saleor_product.store_value_in_private_metadata({'publish.type': offer_type})
    saleor_product.is_published = False
    saleor_product.save(update_fields=["is_published"])
    # New offer
    if saleor_product.get_value_from_private_metadata(
            'publish.allegro.status') == ProductPublishState.MODERATED.value and \
            saleor_product.get_value_from_private_metadata(
                "publish.allegro.date") is None and saleor_product.is_published is False:

        saleor_product.is_published = True
        saleor_product.save(update_fields=["is_published"])

        product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type, product_images, 'required')
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
                'publish.allegro.date') is not None and \
            saleor_product.is_published is False:

        offer_id = saleor_product.private_metadata.get('publish.allegro.id')

        if offer_id:
            product = allegro_api_instance.prepare_offer(saleor_product, starting_at, offer_type,
                                                         product_images, 'required')
            offer_update = allegro_api_instance.update_allegro_offer(allegro_product=product,
                                                                     allegro_id=offer_id)

            description = offer_update.get('description')
            logger.info('Offer update: ' + str(offer_update))
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
