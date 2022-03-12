import hashlib
import json
from json.decoder import JSONDecodeError
import logging
from typing import Any, Dict, Optional

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.utils.html import escape

from ....core.transactions import transaction_with_commit_on_errors
from ....payment.models import Payment, Transaction
from ... import TransactionKind
from ...utils import create_transaction, gateway_postprocess
from ....order.actions import cancel_order, order_captured
from ...interface import GatewayConfig, GatewayResponse
from ....order.events import external_notification_event
from .utils import calculate_payu_price_to_decimal
from ....plugins.manager import get_plugins_manager

logger = logging.getLogger(__name__)


def get_payment(
    payment_token: Optional[str],
    check_if_active=True,
) -> Optional[Payment]:

    if payment_token is None:
        return None

    payments = (
        Payment.objects.prefetch_related("order", "checkout")
            .select_for_update(of=("self",))
            .filter(token=payment_token, gateway="salingo.payments.payu")
    )

    if check_if_active:
        payments = payments.filter(is_active=True)
    payment = payments.first()

    return payment


def get_transaction(
    payment: "Payment", kind: str,
) -> Optional[Transaction]:
    transaction = payment.transactions.filter(kind=kind).last()
    return transaction


def validate_request(request, gateway_config):
    signature = escape(request.META.get('HTTP_OPENPAYU_SIGNATURE')).split(';')
    signature_data = {}
    # split HTTP_OPENPAYU_SIGNATURE into key:value dict
    for param in signature:
        try:
            param = param.split('=')
            signature_data[param[0]] = param[1]
        except IndexError:
            continue
    # check signature and signature algorithm
    try:
        incoming_signature = signature_data['signature']
        incoming_signature_hash_method = signature_data['algorithm']
    except KeyError:
        logger.warning('signature or algorithm is missing')
        return False

    if incoming_signature_hash_method != 'MD5':
        logger.warning('hash method different than md5')
        return False

    second_md5_key = gateway_config.connection_params.get('second_md5').encode('utf-8')
    # validate signature
    expected_signature = hashlib.md5(request.body + second_md5_key).hexdigest()
    if incoming_signature != expected_signature:
        logger.warning('incoming_signature different than expected_signature')
        return False
    return True


@transaction_with_commit_on_errors()
def handle_webhook(request: WSGIRequest, gateway_config: "GatewayConfig"):
    try:
        json_data = json.loads(request.body)
    except JSONDecodeError:
        return HttpResponse(status=400)

    notification = json_data.get("order")
    # auth validation
    if not validate_request(request, gateway_config):
        return HttpResponse(status=403)

    event_handler = EVENT_MAP.get(notification.get("status", ""))
    if event_handler:
        event = event_handler(notification, gateway_config)
        if event == 200:
            return HttpResponse(status=200)
    return HttpResponse(status=400)


def handle_pending(notification: Dict[str, Any], gateway_config: GatewayConfig):
    payment = get_payment(notification.get("extOrderId"))
    if not payment:
        return
    transaction = get_transaction(payment, TransactionKind.PENDING)
    if transaction and transaction.is_success:
        # it is already pending
        return
    new_transaction = create_new_transaction(
        notification, payment, TransactionKind.PENDING
    )
    gateway_postprocess(new_transaction, payment)

    msg = f"Payu: The transaction is pending."
    create_payment_notification_for_order(
        payment, msg, None, new_transaction.is_success
    )

    return 200


def handle_completed(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    payment = get_payment(notification.get("extOrderId"))
    manager = get_plugins_manager()
    if not payment:
        return
    capture_transaction = payment.transactions.filter(
        action_required=False, is_success=True, kind=TransactionKind.CAPTURE,
    ).last()

    new_transaction = create_new_transaction(
        notification, payment, TransactionKind.CAPTURE
    )

    if new_transaction.is_success and not capture_transaction:
        gateway_postprocess(new_transaction, payment)
        order_captured(order=payment.order,
                       user=None,
                       amount=new_transaction.amount,
                       payment=payment,
                       manager=manager,
                       app=None)

    reason = notification.get("reason", "-")
    is_success = True
    success_msg = f"Payu: The capture request was successful."
    failed_msg = f"Payu: The capture request failed."
    create_payment_notification_for_order(payment, success_msg, failed_msg, is_success)

    if new_transaction.is_success and not capture_transaction:
        return 200
    else:
        return 400


def handle_cancellation(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    payment = get_payment(notification.get("extOrderId"))

    if not payment:
        return
    transaction = get_transaction(payment, TransactionKind.CANCEL)
    if transaction and transaction.is_success:
        # it is already cancelled
        return
    new_transaction = create_new_transaction(
        notification, payment, TransactionKind.CANCEL
    )
    gateway_postprocess(new_transaction, payment)

    reason = notification.get("reason", "-")
    success_msg = f"Payu: The cancel request was successful."
    failed_msg = f"Payu: The cancel request failed."
    create_payment_notification_for_order(
        payment, success_msg, failed_msg, new_transaction.is_success
    )
    if payment.order and new_transaction.is_success:
        cancel_order(payment.order, None)

    return 200


def create_new_transaction(notification, payment, kind):
    currency = notification.get("currencyCode")
    amount = notification.get("totalAmount")
    amount = calculate_payu_price_to_decimal(amount)

    is_success = True

    gateway_response = GatewayResponse(
        kind=kind,
        action_required=False,
        transaction_id="",
        is_success=is_success,
        amount=amount,
        currency=currency,
        error="",
        raw_response={},
    )
    return create_transaction(
        payment,
        kind=kind,
        payment_information=None,
        action_required=False,
        gateway_response=gateway_response,
    )


def create_payment_notification_for_order(
    payment: Payment, success_msg: str, failed_msg: Optional[str], is_success: bool
):
    if not payment.order:
        # Order is not assigned
        return
    msg = success_msg if is_success else failed_msg

    external_notification_event(
        order=payment.order,
        user=None,
        app=None,
        message=msg,
        parameters={"service": payment.gateway, "id": payment.token},
    )


EVENT_MAP = {
    "PENDING": handle_pending,
    "COMPLETED": handle_completed,
    "CANCELED": handle_cancellation
}
