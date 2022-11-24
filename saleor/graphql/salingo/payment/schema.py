import graphene

from .types import PaymentUrl
from saleor.graphql.core.utils import from_global_id_or_error
from saleor.graphql.payment.types import Payment
from saleor.payment import models
from saleor.plugins.manager import get_plugins_manager
from saleor.payment.gateways.payu.utils import generate_payu_redirect_url
from saleor.payment.utils import create_payment_information


class PaymentQueries(graphene.ObjectType):
    generate_payment_url = graphene.Field(
        PaymentUrl,
        description="Generates an url to redirect to payment gateway and complete payment",
        payment_id=graphene.Argument(
            graphene.ID,
            description="Payment ID.",
            required=True
        ),
        channel=graphene.String()
    )

    def resolve_generate_payment_url(self, info, **kwargs):
        value, payment_id = from_global_id_or_error(
            kwargs["payment_id"], only_type=Payment
        )
        channel = kwargs["channel"]
        payment = models.Payment.objects.filter(id=payment_id).first()
        manager = get_plugins_manager()
        plugin = manager.get_plugin(plugin_id=payment.gateway, channel_slug=channel)
        config = plugin.get_payment_connection_params(plugin.configuration)
        redirect_url = generate_payu_redirect_url(config,
                                                  create_payment_information(payment))
        return PaymentUrl(payment_url=redirect_url)
