import logging
from datetime import datetime
import pytz

from ...celeryconf import app
from .utils import ParametersMapperFactory, ProductMapperFactory, AllegroAPI, email_errors
from saleor.product.models import Product

logger = logging.getLogger(__name__)
from saleor.plugins.allegro import ProductPublishState

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
    saleor_product.is_published = is_published
    saleor_product.save(update_fields=["is_published"])

    if saleor_product.get_value_from_private_metadata(
            'publish.allegro.status') == ProductPublishState.MODERATED.value and \
            saleor_product.get_value_from_private_metadata(
                "publish.allegro.date") is None and saleor_product.is_published is False:

        saleor_product.is_published = True
        saleor_product.save(update_fields=["is_published"])

        product = allegro_api_instance.prepare_for_offer(saleor_product, starting_at, offer_type, product_images, 'required')
        offer = allegro_api_instance.publish_to_allegro(allegro_product=product)

        if offer is None:
            allegro_api_instance.update_errors_in_private_metadata(
                saleor_product,
                [error for error in allegro_api_instance.errors])

            if products_bulk_ids: email_errors(products_bulk_ids)
            return
        # Save errors if they exist
        err_handling_response = AllegroAPI.error_handling(offer, allegro_api_instance, saleor_product, ProductPublishState, 'old')
        # If must_assign_offer_to_product create new product with an offer
        if err_handling_response == 'must_assign_offer_to_product':
            product = allegro_api_instance.prepare_for_offer(saleor_product, starting_at, offer_type, product_images, 'requiredForProduct')
            offer = allegro_api_instance.publish_to_allegro_product_create(product)
            if offer is None:
                allegro_api_instance.update_errors_in_private_metadata(
                    saleor_product,
                    [error for error in allegro_api_instance.errors])
                return
            err_handling_response = AllegroAPI.error_handling(offer, allegro_api_instance, saleor_product, ProductPublishState, 'new')

        if products_bulk_ids:
            email_errors(products_bulk_ids)
        return

    if saleor_product.get_value_from_private_metadata('publish.allegro.status') == \
            ProductPublishState.MODERATED.value and \
            saleor_product.get_value_from_private_metadata(
                'publish.allegro.date') is not None and \
            saleor_product.is_published is False:

        offer_id = saleor_product.private_metadata.get('publish.allegro.id')

        if offer_id is not None:
            product = allegro_api_instance.prepare_for_offer(saleor_product, starting_at, offer_type, product_images, 'required')
            #offer_update = allegro_api_instance.update_allegro_offer(allegro_product=product, allegro_id=offer_id)
            offer_update = allegro_api_instance.publish_to_allegro_product_create(product)
            logger.info('Offer update: ' + str(offer_update))
            offer = allegro_api_instance.valid_offer(offer_id)
            # Save errors if they exist
            err_handling_response = AllegroAPI.error_handling(offer, allegro_api_instance, saleor_product, ProductPublishState, 'old')
            # If must_assign_offer_to_product create new product with an offer
            if err_handling_response == 'must_assign_offer_to_product':
                pass
                # TODO

    if products_bulk_ids: email_errors(products_bulk_ids)
