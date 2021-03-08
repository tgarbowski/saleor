from celery import shared_task

import logging
logger = logging.getLogger(__name__)

from saleor.plugins.allegro import ProductPublishState


@shared_task
def async_product_publish(self, saleor_product, offer_type, starting_at):
    return _product_publish_test(self, saleor_product, offer_type, starting_at)
    #return _product_publish(self, saleor_product, offer_type, starting_at)

def _product_publish_test(self, saleor_product, offer_type, starting_at):
    print('this should work asyc')
    pass

def _product_publish(self, saleor_product, offer_type, starting_at):
        if saleor_product.get_value_from_private_metadata(
                'publish.allegro.status') == self.ProductPublishState.MODERATED.value and \
                saleor_product.get_value_from_private_metadata(
                    "publish.allegro.date") is None and \
                saleor_product.is_published is False:

            saleor_product.is_published = True
            saleor_product.save(update_fields=["is_published"])

            category_id = saleor_product.product_type.metadata.get(
                'allegro.mapping.categoryId')

            require_parameters = self.get_require_parameters(category_id)

            parameters_mapper = self.ParametersMapperFactory().get_mapper()

            parameters = parameters_mapper.set_product(
                saleor_product).set_require_parameters(require_parameters).run_mapper()

            product_mapper = self.ProductMapperFactory().get_mapper()

            try:
                product = product_mapper.set_saleor_product(saleor_product) \
                    .set_saleor_images(self.upload_images(saleor_product)) \
                    .set_saleor_parameters(parameters).set_obj_publication_starting_at(
                    starting_at).set_offer_type(offer_type).set_category(
                    category_id).run_mapper()
            except IndexError as err:
                self.errors.append(str(err))
                self.update_errors_in_private_metadata(saleor_product,
                                                       [error for error in self.errors])
                return

            offer = self.publish_to_allegro(allegro_product=product)
            if offer is None:
                self.update_errors_in_private_metadata(saleor_product,
                                                       [error for error in self.errors])
                return None
            if 'error' in offer:
                self.errors.append(offer.get('error_description'))
                self.update_errors_in_private_metadata(saleor_product,
                                                       [error for error in self.errors])
                return None
            elif 'errors' in offer:
                self.errors += offer['errors']
                self.update_errors_in_private_metadata(saleor_product, [
                    error.get('message') if type(error) is not str else error for error
                    in self.errors])
                return None
            else:
                if offer is not None and offer.get('validation').get(
                        'errors') is not None:
                    if len(offer['validation'].get('errors')) > 0:
                        for error in offer['validation'].get('errors'):
                            logger.error((error[
                                              'message'] + ' dla ogłoszenia: ' + self.env + '/offer/' +
                                          offer['id'] + '/restore'))
                            self.errors.append((error[
                                                    'message'] + ' dla ogłoszenia: ' + self.env + '/offer/' +
                                                offer['id'] + '/restore'))
                        self.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.MODERATED.value, False, self.errors)
                    else:
                        offer_publication = self.offer_publication(offer['id'])
                        self.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.PUBLISHED.value, True, self.errors)

                return offer['id']

        if saleor_product.get_value_from_private_metadata('publish.allegro.status') == \
                ProductPublishState.MODERATED.value and \
                saleor_product.get_value_from_private_metadata(
                    'publish.allegro.date') is not None and \
                saleor_product.is_published is False:
            offer_id = saleor_product.private_metadata.get('publish.allegro.id')
            if offer_id is not None:
                offer_update = self.update_offer(saleor_product, starting_at,
                                                 offer_type)
                logger.info('Offer update: ' + str(offer_update))

                offer = self.valid_offer(offer_id)

                if 'error' in offer:
                    self.errors.append(offer.get('error_description'))
                    self.update_errors_in_private_metadata(saleor_product,
                                                           [error for error in
                                                            self.errors])
                elif 'errors' in offer:
                    self.errors += offer['errors']
                    self.update_errors_in_private_metadata(saleor_product,
                                                           [error.get('message') for
                                                            error in self.errors])
                elif offer['validation'].get('errors') is not None:
                    if len(offer['validation'].get('errors')) > 0:
                        for error in offer['validation'].get('errors'):
                            logger.error((error[
                                              'message'] + ' dla ogłoszenia: ' + self.env + '/offer/' +
                                          offer['id'] + '/restore'))
                            self.errors.append((error[
                                                    'message'] + 'dla ogłoszenia: ' + self.env + '/offer/' +
                                                offer['id'] + '/restore'))
                        self.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.MODERATED.value, False, self.errors)
                    else:
                        self.offer_publication(
                            saleor_product.private_metadata.get('publish.allegro.id'))
                        self.update_status_and_publish_data_in_private_metadata(
                            saleor_product, offer['id'],
                            ProductPublishState.PUBLISHED.value, True, self.errors)
