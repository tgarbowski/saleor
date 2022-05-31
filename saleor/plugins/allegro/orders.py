from datetime import datetime, timedelta
from typing import Dict, List
import json

from graphql_relay import from_global_id, to_global_id
import requests

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.conf import settings

from saleor.order.models import Order
from saleor.product.models import ProductVariant
from saleor.app.models import App

from saleor.order.actions import mark_order_as_paid
from saleor.plugins.manager import get_plugins_manager
from saleor.shipping.models import ShippingMethod
from saleor.order.models import Voucher
from saleor.app.models import AppToken
from saleor.channel.models import Channel


DRAFT_ORDER_CREATE_MUTATION = """
    mutation draftCreate(
        $user: ID, $discount: PositiveDecimal, $lines: [OrderLineCreateInput],
        $shippingAddress: AddressInput, $billingAddress: AddressInput,
        $shippingMethod: ID, $voucher: ID, $customerNote: String, $channel: ID,
        $redirectUrl: String
        ) {
            draftOrderCreate(
                input: {user: $user, discount: $discount,
                lines: $lines, shippingAddress: $shippingAddress,
                billingAddress: $billingAddress,
                shippingMethod: $shippingMethod, voucher: $voucher,
                channelId: $channel,
                redirectUrl: $redirectUrl,
                customerNote: $customerNote}) {
                    errors {
                        field
                        code
                        variants
                        message
                        addressType
                    }
                    order {
                        id
                    }
                }
        }
    """

DRAFT_ORDER_COMPLETE_MUTATION = """
    mutation draftComplete($id: ID!) {
        draftOrderComplete(id: $id) {
            errors {
                field
                code
                message
                variants
            }
            order {
                status
                origin
            }
        }
    }
"""


def get_allegro_shipping_address(checkout_form):
    shipping_address = {
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
    return shipping_address


def get_allegro_billing_address(checkout_form):
    billing_address = {
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
    return billing_address


def get_shipping_method_by_name(allegro_shipping_name: str) -> "ShippingMethod":
    shipping_method = ShippingMethod.objects.filter(name=allegro_shipping_name).first()

    # TODO: return None here
    if not shipping_method:
        shipping_method = None

    return shipping_method


def is_smart(checkout_form: dict) -> bool:
    return checkout_form['delivery']['smart']


def prepare_variant_list(line_items: dict) -> list:
    variant_list = []

    for line_item in line_items:
        sku = line_item['offer']['external']['id']
        quantity = int(line_item['quantity'])

        product_variant = ProductVariant.objects.get(sku=sku)
        variant_id = to_global_id("ProductVariant", product_variant.id)
        variant_list.append(
            {"variantId": variant_id, "quantity": quantity}
        )
    return variant_list


def get_processed_allegro_orders_ids(past_days: int) -> List[int]:
    date_from = timezone.now() - timedelta(days=past_days)

    allegro_orders_ids = Order.objects.filter(
        metadata__allegro_order_id__isnull=False,
        created__gte=date_from
    ).values_list('metadata__allegro_order_id', flat=True)

    return list(allegro_orders_ids)


def filter_unprocessed_orders(checkout_forms, processed_allegro_orders_ids):
    checkout_forms = [checkout_form for checkout_form in checkout_forms
                      if checkout_form['id'] not in processed_allegro_orders_ids]

    return checkout_forms


def get_allegro_orders(channel_slug: str, past_days: int) -> List[Dict]:
    from .api import AllegroAPI

    allegro_api = AllegroAPI(channel=channel_slug)

    updated_at_from = timezone.now() - timedelta(days=past_days)
    updated_at_from = datetime.strftime(updated_at_from, "%Y-%m-%dT%H:%M:%S")

    statuses = ['READY_FOR_PROCESSING']

    orders = allegro_api.get_orders(statuses=statuses, updated_at_from=updated_at_from)

    return orders['checkoutForms']


def prepare_draft_order_create_input(checkout_form, channel_global_id):
    shipping_address = get_allegro_shipping_address(checkout_form)
    billing_address = get_allegro_billing_address(checkout_form)

    line_items = checkout_form['lineItems']
    variant_list = prepare_variant_list(line_items)

    delivery_method_name = checkout_form['delivery']['method']['name']
    shipping_method = get_shipping_method_by_name(delivery_method_name)

    if shipping_method:
        shipping_method_id = to_global_id("ShippingMethod", shipping_method.id)
    else:
        shipping_method_id = None

    draft_order_create_input = {
        "lines": variant_list,
        "billingAddress": billing_address,
        "shippingAddress": shipping_address,
        "shippingMethod": shipping_method_id,
        "channel": channel_global_id
    }

    smart = checkout_form['delivery']['smart']
    # Make delivery free in case of SMART package
    if smart:
        voucher = Voucher.objects.get(name='SMART')
        voucher_id = to_global_id("Voucher", voucher.id)
        draft_order_create_input['voucher'] = voucher_id

    return draft_order_create_input


def post_graphql(query, variables=None):
    data = {"query": query}
    if variables is not None:
        data["variables"] = variables

    data = json.dumps(data, cls=DjangoJSONEncoder)

    app_token = AppToken.objects.get(app__name='orders').auth_token

    headers = {
        "content-type": "application/json",
        "Authorization": f'Bearer {app_token}'
    }

    result = requests.post(url=settings.API_URI, data=data, headers=headers)
    return result.json()


def save_allegro_order(checkout_form, channel_global_id):
    app = App.objects.get(name='orders')

    allegro_order_id = checkout_form['id']
    user_email = checkout_form['buyer']['email']
    # delivery_cost = checkout_form['delivery']['cost']['amount']
    delivery_method_name = checkout_form['delivery']['method']['name']
    smart = checkout_form['delivery']['smart']
    draft_order_create_input = prepare_draft_order_create_input(checkout_form, channel_global_id)
    pickup_point = checkout_form['delivery'].get('pickupPoint')
    pickup_point_id = pickup_point['id'] if pickup_point else None

    draft_order_create_response = post_graphql(
        DRAFT_ORDER_CREATE_MUTATION,
        draft_order_create_input
    )

    order_id = draft_order_create_response['data']['draftOrderCreate']['order']['id']
    order = from_global_id(order_id)
    order = Order.objects.get(pk=order[1])
    # Store additional order data
    order.user_email = user_email
    order.shipping_method_name = delivery_method_name
    order.store_value_in_metadata(
        {"allegro_order_id": allegro_order_id,
         "smart": smart
        }
    )
    if pickup_point_id:
        order.store_value_in_metadata({"locker_id": pickup_point_id})
    order.save()
    # Complete order
    draft_order_complete_input = {"id": order_id}
    draft_order_complete_response = post_graphql(
        DRAFT_ORDER_COMPLETE_MUTATION,
        draft_order_complete_input
    )

    if draft_order_complete_response['data']['draftOrderComplete']['errors']:
        return
    # Mark order as paid
    manager = get_plugins_manager()

    mark_order_as_paid(
        order=order,
        request_user=None,
        manager=manager,
        app=app
    )


def insert_allegro_orders(channel_slug, past_days):
    orders = get_allegro_orders(channel_slug=channel_slug, past_days=past_days)
    # Get already processed orders from db last x days
    processed_allegro_orders_ids = get_processed_allegro_orders_ids(past_days=past_days)
    # Filter processed orders from allegro orders
    unprocessed_orders = filter_unprocessed_orders(orders, processed_allegro_orders_ids)
    # For each order insert to db
    channel = Channel.objects.get(slug=channel_slug)
    channel_global_id = to_global_id("Channel", channel.id)

    for unprocessed_order in unprocessed_orders:
        save_allegro_order(checkout_form=unprocessed_order, channel_global_id=channel_global_id)
