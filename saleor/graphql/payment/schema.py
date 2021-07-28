import graphene

from ...core.permissions import OrderPermissions
from ..core.fields import PrefetchingConnectionField
from ..decorators import permission_required
from .mutations import PaymentCapture, PaymentInitialize, PaymentRefund, PaymentVoid
from .resolvers import resolve_payments, resolve_generate_payment_url
from .types import Payment, PaymentUrl


class PaymentQueries(graphene.ObjectType):
    payment = graphene.Field(
        Payment,
        description="Look up a payment by ID.",
        id=graphene.Argument(
            graphene.ID, description="ID of the payment.", required=True
        ),
    )
    payments = PrefetchingConnectionField(Payment, description="List of payments.")

    generate_payment_url = graphene.Field(PaymentUrl, description="Generates an url to redirect to payment gateway and complete payment",
                                          checkout_id=graphene.Argument(graphene.ID,
                                              description="Checkout ID.", required=True)
                                          )

    @permission_required(OrderPermissions.MANAGE_ORDERS)
    def resolve_payment(self, info, **data):
        return graphene.Node.get_node_from_global_id(info, data.get("id"), Payment)

    @permission_required(OrderPermissions.MANAGE_ORDERS)
    def resolve_payments(self, info, query=None, **_kwargs):
        return resolve_payments(info, query)

    @staticmethod
    def resolve_generate_payment_url(self, info, **_kwargs):
        return resolve_generate_payment_url(info, **_kwargs)


class PaymentMutations(graphene.ObjectType):
    payment_capture = PaymentCapture.Field()
    payment_refund = PaymentRefund.Field()
    payment_void = PaymentVoid.Field()
    payment_initialize = PaymentInitialize.Field()
