from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from typing import Dict, List, Optional

from graphene.utils.str_converters import to_snake_case
from graphql_relay import from_global_id, to_global_id

from django.utils import timezone

from saleor.account.forms import get_address_form
from saleor.order.models import Order
from saleor.product.models import ProductVariant, ProductVariantChannelListing
from saleor.app.models import App
from saleor.order.actions import mark_order_as_paid
from saleor.plugins.manager import get_plugins_manager
from saleor.shipping.models import ShippingMethod
from saleor.channel.models import Channel
from saleor.salingo.orders import (DRAFT_ORDER_CREATE_MUTATION, DRAFT_ORDER_COMPLETE_MUTATION,
                                   MUTATION_ORDER_CANCEL, InternalApiClient)
from saleor.plugins.allegro.utils import get_datetime_now
from saleor.plugins.allegro.api import AllegroAPI
from saleor.plugins.allegro import ProductPublishState
from saleor.discount.models import Sale
from saleor.plugins.allegro.utils import format_allegro_datetime
from saleor.order.utils import recalculate_order


TWO_PLACES = Decimal("0.01")
logger = logging.getLogger(__name__)


@dataclass
class AllegroOrderPosition:
    quantity: int
    sku: str = ''
    sale_date: str = ''
    price: Decimal = None


class AllegroOrderExtractor:
    @staticmethod
    def shipping_address(checkout_form) -> Dict:
        return {
            'firstName': checkout_form['delivery']['address']['firstName'],
            'lastName': checkout_form['delivery']['address']['lastName'],
            'companyName': '',
            'streetAddress1': checkout_form['delivery']['address']['street'],
            'city': checkout_form['delivery']['address']['city'],
            'postalCode': checkout_form['delivery']['address']['zipCode'],
            'country': checkout_form['delivery']['address']['countryCode'],
            'phone': checkout_form['delivery']['address']['phoneNumber'],
            'vatId': ''
        }

    @staticmethod
    def billing_address(checkout_form) -> Dict:
        if AllegroOrderExtractor.is_invoice(checkout_form):
            return AllegroOrderExtractor.billing_address_invoice(checkout_form)
        else:
            return AllegroOrderExtractor.regular_billing_address(checkout_form)

    @staticmethod
    def regular_billing_address(checkout_form) -> Dict:
        return {
            'firstName': checkout_form['buyer']['firstName'],
            'lastName': checkout_form['buyer']['lastName'],
            'companyName': '',
            'phone': checkout_form['buyer']['phoneNumber'],
            'streetAddress1': checkout_form['buyer']['address']['street'],
            'city': checkout_form['buyer']['address']['city'],
            'postalCode': checkout_form['buyer']['address']['postCode'],
            'country': checkout_form['buyer']['address']['countryCode'],
            'vatId': ''
        }

    @staticmethod
    def billing_address_invoice(checkout_form) -> Dict:
        address = {
            'firstName': '',
            'lastName': '',
            'companyName': '',
            'phone': '',
            'streetAddress1': checkout_form['invoice']['address'].get('street', ''),
            'city': checkout_form['invoice']['address'].get('city', ''),
            'postalCode': checkout_form['invoice']['address'].get('zipCode', ''),
            'country': checkout_form['invoice']['address'].get('countryCode', ''),
            'vatId': ''
        }

        if checkout_form['invoice']['address']['naturalPerson']:
            address['firstName'] = checkout_form['invoice']['address']['naturalPerson'].get('firstName', '')
            address['lastName'] = checkout_form['invoice']['address']['naturalPerson'].get('lastName', '')

        if checkout_form['invoice']['address']['company']:
            address['companyName'] = checkout_form['invoice']['address']['company'].get('name', '')
            address['vatId'] = checkout_form['invoice']['address']['company'].get('taxId', '')

        return address

    @staticmethod
    def is_smart(checkout_form: dict) -> bool:
        return checkout_form['delivery']['smart']

    @staticmethod
    def is_invoice(checkout_form: dict) -> bool:
        return checkout_form['invoice']['required']

    @staticmethod
    def delivery_method_name(checkout_form) -> str:
        return checkout_form['delivery']['method']['name']

    @staticmethod
    def buyer_email(checkout_form) -> str:
        return checkout_form['buyer']['email']

    @staticmethod
    def customer_note(checkout_form) -> str:
        return checkout_form['messageToSeller']

    @staticmethod
    def pickup_point_id(checkout_form) -> Optional[str]:
        pickup_point = checkout_form['delivery'].get('pickupPoint')
        return pickup_point['id'] if pickup_point else None

    @staticmethod
    def order_positions(line_items) -> List[AllegroOrderPosition]:
        positions = []
        for line_item in line_items:
            position = AllegroOrderPosition(
                sku=line_item['offer']['external']['id'],
                sale_date=format_allegro_datetime(line_item['boughtAt']),
                price=Decimal(line_item['price']['amount']).quantize(TWO_PLACES),
                quantity=line_item['quantity']
            )
            positions.append(position)
        return positions

    @staticmethod
    def order_id(checkout_form):
        return checkout_form['id']

    @staticmethod
    def shipping_cost(checkout_form):
        return checkout_form['delivery']['cost']['amount']


def prepare_draft_order_lines(line_items: List[AllegroOrderPosition]) -> List:
    variant_list = []
    # TODO: 1 query, join products
    for line_item in line_items:
        product_variant = ProductVariant.objects.get(sku=line_item.sku)

        remove_product_discounts(product=product_variant.product)
        update_price(variant_id=product_variant.pk, price_amount=line_item.price)

        variant_list.append(
            {
                "variantId": to_global_id("ProductVariant", product_variant.id),
                "quantity": line_item.quantity
            }
        )
    return variant_list


def filter_unprocessed_orders(checkout_forms, processed_allegro_orders_ids):
    # TODO: processed_allegro_orders_ids as set
    checkout_forms = [checkout_form for checkout_form in checkout_forms
                      if checkout_form['id'] not in processed_allegro_orders_ids]

    return checkout_forms


def get_allegro_orders(
    channel_slug: str,
    datetime_from: str,
    statuses: List[str],
    fulfillment_statuses: List[str]
) -> List[Dict]:
    allegro_api = AllegroAPI(channel=channel_slug)
    orders = allegro_api.get_orders(
        statuses=statuses,
        fulfillment_statuses=fulfillment_statuses,
        updated_at_from=datetime_from
    )
    return orders


def prepare_draft_order_create_input(checkout_form, channel_id):
    allegro_positions = AllegroOrderExtractor.order_positions(checkout_form['lineItems'])
    lines = prepare_draft_order_lines(allegro_positions)

    delivery_method_name = AllegroOrderExtractor.delivery_method_name(checkout_form)

    shipping_method = get_shipping_method_by_name(delivery_method_name)

    if shipping_method:
        shipping_method_id = to_global_id("ShippingMethod", shipping_method.id)
    else:
        shipping_method_id = None

    draft_order_create_input = {
        "lines": lines,
        "billingAddress": AllegroOrderExtractor.billing_address(checkout_form),
        "shippingAddress": AllegroOrderExtractor.shipping_address(checkout_form),
        "shippingMethod": shipping_method_id,
        "channel": to_global_id("Channel", channel_id),
        "customerNote": AllegroOrderExtractor.customer_note(checkout_form)
    }
    # Allegro billing address might be invalid, set it to shipping address in that case
    if not validate_camel_case_address(draft_order_create_input['billingAddress']):
        draft_order_create_input['billingAddress'] = draft_order_create_input['shippingAddress']
    return draft_order_create_input


def validate_camel_case_address(address: dict) -> bool:
    model_arguments = {to_snake_case(k): v for k, v in address.items()}
    model_arguments['street_address_1'] = model_arguments['street_address1']
    address_form = get_address_form(model_arguments, country_code=model_arguments['country'])[0]
    return address_form.is_valid()


def save_additional_allegro_order_data(order, checkout_form):
    pickup_point_id = AllegroOrderExtractor.pickup_point_id(checkout_form)

    order.user_email = mangle_email(AllegroOrderExtractor.buyer_email(checkout_form))
    order.shipping_method_name = AllegroOrderExtractor.delivery_method_name(checkout_form)
    order.store_value_in_metadata(
        {
            "allegro_order_id": AllegroOrderExtractor.order_id(checkout_form),
            "smart": AllegroOrderExtractor.is_smart(checkout_form)
        }
    )
    if pickup_point_id:
        order.store_value_in_metadata({"locker_id": pickup_point_id})

    if AllegroOrderExtractor.is_invoice(checkout_form):
        order.store_value_in_metadata({"invoice": "true"})
    else:
        order.store_value_in_metadata({"invoice": "false"})

    order.save()


def insert_allegro_orders(channel_slug: str, datetime_from: str):
    orders = get_allegro_orders(
        channel_slug=channel_slug,
        datetime_from=datetime_from,
        statuses=['READY_FOR_PROCESSING'],
        fulfillment_statuses=['NEW']
    )

    processed_allegro_orders_ids = get_processed_not_canceled_allegro_orders_ids(
        channel_slug=channel_slug,
        datetime_from=datetime.strptime(datetime_from, "%Y-%m-%dT%H:%M:%S")
    )
    unprocessed_orders = filter_unprocessed_orders(orders, processed_allegro_orders_ids)

    channel_id = Channel.objects.get(slug=channel_slug).pk
    api_client = InternalApiClient(app=get_order_app())

    for unprocessed_order in unprocessed_orders:
        allegro_order_id = AllegroOrderExtractor.order_id(unprocessed_order)
        logger.info(f'Processing allegro order {allegro_order_id} in channel {channel_slug}')
        try:
            insert_allegro_order(
                api_client=api_client,
                checkout_form=unprocessed_order,
                channel_id=channel_id
            )
        except ProductVariant.DoesNotExist:
            error_message = f'Missing products for allegro order {allegro_order_id} in channel {channel_slug}'
            logger.error(error_message)


def insert_allegro_order(api_client, checkout_form, channel_id) -> Optional[int]:
    # Create draft order
    draft_order_create_input = prepare_draft_order_create_input(checkout_form, channel_id)
    draft_order_create_response = api_client.post_graphql(
        DRAFT_ORDER_CREATE_MUTATION,
        draft_order_create_input
    ).json()
    if draft_order_create_response['data']['draftOrderCreate']['errors']:
        logger.error('Draft order create error')
        logger.error(draft_order_create_response['data']['draftOrderCreate']['errors'])
        return
    order_id_global = draft_order_create_response['data']['draftOrderCreate']['order']['id']
    order = get_order_from_global_id(order_id_global)
    # Save sold products private metadata
    allegro_positions = AllegroOrderExtractor.order_positions(checkout_form['lineItems'])
    for allegro_position in allegro_positions:
        update_sold_product_private_metadata(allegro_position)
    # Store additional order data
    save_additional_allegro_order_data(order=order, checkout_form=checkout_form)
    # Set shipping_price and recalculate order
    shipping_price = AllegroOrderExtractor.shipping_cost(checkout_form)
    update_shipping_price(order=order, price=Decimal(shipping_price))
    recalculate_order(order=order)
    # Complete order
    draft_order_complete_input = {"id": order_id_global}
    draft_order_complete_response = api_client.post_graphql(
        DRAFT_ORDER_COMPLETE_MUTATION,
        draft_order_complete_input
    ).json()

    if draft_order_complete_response['data']['draftOrderComplete']['errors']:
        logger.error('Draft order complete error')
        logger.error(draft_order_complete_response['data']['draftOrderComplete']['errors'])
        return
    # Mark order as paid
    mark_order_as_paid(
        order=order,
        request_user=None,
        manager=get_plugins_manager(),
        app=api_client.app
    )
    return order.id


def cancel_allegro_orders(channel_slug: str, datetime_from: str):
    orders = get_allegro_orders(
        channel_slug=channel_slug,
        datetime_from=datetime_from,
        statuses=['CANCELED'],
        fulfillment_statuses=[]
    )

    processed_allegro_orders_ids = get_processed_not_canceled_allegro_orders_ids(
        channel_slug=channel_slug,
        datetime_from=datetime.strptime(datetime_from, "%Y-%m-%dT%H:%M:%S")
    )
    unprocessed_orders = filter_unprocessed_orders(orders, processed_allegro_orders_ids)
    api_client = InternalApiClient(app=get_order_app())

    for unprocessed_order in unprocessed_orders:
        cancel_allegro_order(api_client=api_client, checkout_form=unprocessed_order)


def cancel_allegro_order(api_client, checkout_form):
    allegro_order_id = AllegroOrderExtractor.order_id(checkout_form)
    order = get_order_by_allegro_id(allegro_order_id)
    cancel_order_input = {"id": to_global_id("Order", order.pk)}

    order_cancel_response = api_client.post_graphql(
        MUTATION_ORDER_CANCEL,
        cancel_order_input
    ).json()

    if order_cancel_response['data']['orderCancel']['errors']:
        logger.error('Cancel order error')
        return

    allegro_positions = AllegroOrderExtractor.order_positions(checkout_form['lineItems'])
    for allegro_position in allegro_positions:
        update_cancelled_order_products_private_metadata(allegro_position)


# DB read queries
def get_processed_not_canceled_allegro_orders_ids(channel_slug: str, datetime_from: datetime) -> List[int]:
    allegro_orders_ids = Order.objects.filter(
        metadata__allegro_order_id__isnull=False,
        created__gte=datetime_from,
        channel__slug=channel_slug
    ).exclude(status='canceled').values_list('metadata__allegro_order_id', flat=True)

    return list(allegro_orders_ids)


def get_shipping_method_by_name(shipping_method_name: str) -> "ShippingMethod":
    return ShippingMethod.objects.filter(
        metadata__allegro_name=shipping_method_name
    ).first()


def get_order_by_allegro_id(allegro_id: str) -> Order:
    return Order.objects.get(metadata__allegro_order_id=allegro_id)


def get_order_from_global_id(order_id_global: str) -> Order:
    order_id = from_global_id(order_id_global)
    return Order.objects.get(pk=order_id[1])


def get_order_app():
    return App.objects.get(name='orders')

# DB write queries
def update_sold_product_private_metadata(product_data: AllegroOrderPosition):
    """Saves allegro related private metadata"""
    try:
        product = ProductVariant.objects.get(sku=product_data.sku).product
    except ProductVariant.DoesNotExist:
        return

    product.store_value_in_private_metadata(
        {
            'publish.status.date': product_data.sale_date,
            'publish.allegro.price': product_data.price,
            'publish.allegro.status': ProductPublishState.SOLD.value
        }
    )
    product.save(update_fields=["private_metadata"])


def update_cancelled_order_products_private_metadata(product_data: AllegroOrderPosition):
    try:
        product = ProductVariant.objects.get(sku=product_data.sku).product
    except ProductVariant.DoesNotExist:
        return

    if is_product_sold(product):
        product.store_value_in_private_metadata({'publish.status.date': get_datetime_now()})
        product.delete_value_from_private_metadata('publish.allegro.price')
        product.save(update_fields=["private_metadata"])


def update_price(variant_id, price_amount):
    pvcl = ProductVariantChannelListing.objects.get(variant_id=variant_id)
    pvcl.price_amount = price_amount
    pvcl.save(update_fields=['price_amount'])


def remove_product_discounts(product):
    sales = Sale.objects.all()
    for sale in sales:
        sale.products.remove(product)


def update_shipping_price(order: Order, price: Decimal):
    order.shipping_price_net_amount = price
    order.shipping_price_gross_amount = price
    order.save()

# Parsers
def is_product_sold(product) -> bool:
    return product.private_metadata.get('publish.allegro.status') == ProductPublishState.SOLD.value


def datetime_minus_days(days: int):
    updated_at_from = timezone.now() - timedelta(days=days)
    updated_at_from = datetime.strftime(updated_at_from, "%Y-%m-%dT%H:%M:%S")
    return updated_at_from


def mangle_email(email: str) -> str:
    return email.replace('@', '@mangled-')


def unmangle_email(email: str) -> str:
    return email.replace('@mangled-', '@')

