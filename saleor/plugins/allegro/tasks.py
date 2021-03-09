import logging

from ...celeryconf import app

logger = logging.getLogger(__name__)
from saleor.plugins.allegro import ProductPublishState

@app.task
def async_product_publish(allegro_api_instance, saleor_product, offer_type, starting_at, parameters_mapper_factory, product_mapper_factory):
    return _product_publish(allegro_api_instance, saleor_product, offer_type, starting_at, parameters_mapper_factory, product_mapper_factory)

def _product_publish(allegro_api_instance, saleor_product, offer_type, starting_at, parameters_mapper_factory, product_mapper_factory):
        if saleor_product.get_value_from_private_metadata(
                'publish.allegro.status') == ProductPublishState.MODERATED.value and \
                saleor_product.get_value_from_private_metadata(
                    "publish.allegro.date") is None and \
                saleor_product.is_published is False:

            saleor_product.is_published = True
            saleor_product.save(update_fields=["is_published"])

            category_id = saleor_product.product_type.metadata.get(
                'allegro.mapping.categoryId')

            require_parameters = allegro_api_instance.get_require_parameters(category_id)

            parameters_mapper = parameters_mapper_factory.get_mapper()

            parameters = parameters_mapper.set_product(
                saleor_product).set_require_parameters(require_parameters).run_mapper()

            product_mapper = product_mapper_factory.get_mapper()

            try:
                product = product_mapper.set_saleor_product(saleor_product) \
                    .set_saleor_images(allegro_api_instance.upload_images(saleor_product)) \
                    .set_saleor_parameters(parameters).set_obj_publication_starting_at(
                    starting_at).set_offer_type(offer_type).set_category(
                    category_id).run_mapper()
            except IndexError as err:
                allegro_api_instance.errors.append(str(err))
                allegro_api_instance.update_errors_in_private_metadata(saleor_product,
                                                                       [error for error in allegro_api_instance.errors])
                return

            offer = allegro_api_instance.publish_to_allegro(allegro_product=product)
            if offer is None:
                allegro_api_instance.update_errors_in_private_metadata(saleor_product,
                                                                       [error for error in allegro_api_instance.errors])
                return None
            if 'error' in offer:
                allegro_api_instance.errors.append(offer.get('error_description'))
                allegro_api_instance.update_errors_in_private_metadata(saleor_product,
                                                                       [error for error in allegro_api_instance.errors])
                return None
            elif 'errors' in offer:
                allegro_api_instance.errors += offer['errors']
                allegro_api_instance.update_errors_in_private_metadata(saleor_product, [
                    error.get('message') if type(error) is not str else error for error
                    in allegro_api_instance.errors])
                return None
            else:
                if offer is not None and offer.get('validation').get(
                        'errors') is not None:
                    if len(offer['validation'].get('errors')) > 0:
                        for error in offer['validation'].get('errors'):
                            logger.error((error[
                                              'message'] + ' dla ogłoszenia: ' + allegro_api_instance.env + '/offer/' +
                                          offer['id'] + '/restore'))
                            allegro_api_instance.errors.append((error[
                                                    'message'] + ' dla ogłoszenia: ' + allegro_api_instance.env + '/offer/' +
                                                                offer['id'] + '/restore'))
                        allegro_api_instance.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.MODERATED.value, False, allegro_api_instance.errors)
                    else:
                        offer_publication = allegro_api_instance.offer_publication(offer['id'])
                        allegro_api_instance.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.PUBLISHED.value, True, allegro_api_instance.errors)

                return offer['id']

        if saleor_product.get_value_from_private_metadata('publish.allegro.status') == \
                ProductPublishState.MODERATED.value and \
                saleor_product.get_value_from_private_metadata(
                    'publish.allegro.date') is not None and \
                saleor_product.is_published is False:
            offer_id = saleor_product.private_metadata.get('publish.allegro.id')
            if offer_id is not None:
                offer_update = allegro_api_instance.update_offer(saleor_product, starting_at,
                                                                 offer_type)
                logger.info('Offer update: ' + str(offer_update))

                offer = allegro_api_instance.valid_offer(offer_id)

                if 'error' in offer:
                    allegro_api_instance.errors.append(offer.get('error_description'))
                    allegro_api_instance.update_errors_in_private_metadata(saleor_product,
                                                                           [error for error in
                                                                            allegro_api_instance.errors])
                elif 'errors' in offer:
                    allegro_api_instance.errors += offer['errors']
                    allegro_api_instance.update_errors_in_private_metadata(saleor_product,
                                                                           [error.get('message') for
                                                                            error in allegro_api_instance.errors])
                elif offer['validation'].get('errors') is not None:
                    if len(offer['validation'].get('errors')) > 0:
                        for error in offer['validation'].get('errors'):
                            logger.error((error[
                                              'message'] + ' dla ogłoszenia: ' + allegro_api_instance.env + '/offer/' +
                                          offer['id'] + '/restore'))
                            allegro_api_instance.errors.append((error[
                                                    'message'] + 'dla ogłoszenia: ' + allegro_api_instance.env + '/offer/' +
                                                                offer['id'] + '/restore'))
                        allegro_api_instance.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.MODERATED.value, False, allegro_api_instance.errors)
                    else:
                        allegro_api_instance.offer_publication(
                            saleor_product.private_metadata.get('publish.allegro.id'))
                        allegro_api_instance.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.PUBLISHED.value, True, allegro_api_instance.errors)
