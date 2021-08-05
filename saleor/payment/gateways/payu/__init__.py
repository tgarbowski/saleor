from ... import TransactionKind
from ...interface import GatewayConfig, GatewayResponse, PaymentData


def new_payment(payment_information: PaymentData, config: GatewayConfig) -> GatewayResponse:
    """Perform new payment transaction as pending."""
    return GatewayResponse(
        is_success=True,
        action_required=False,
        kind=TransactionKind.PENDING,
        amount=payment_information.amount,
        currency=payment_information.currency,
        transaction_id="",
        error=None
    )


def process_payment(
    payment_information: PaymentData, config: GatewayConfig
) -> GatewayResponse:
    """Process the payment."""
    return new_payment(payment_information, config)
