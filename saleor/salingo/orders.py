import json

import requests

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from saleor.app.models import AppToken


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


MUTATION_ORDER_CANCEL = """
mutation cancelOrder($id: ID!) {
    orderCancel(id: $id) {
        order {
            status
        }
        errors{
            field
            code
        }
    }
}
"""


class InternalApiClient:
    """Internal GraphQL API client."""
    def __init__(self, app):
        self.app = app

    def post_graphql(self, query, variables=None):
        data = {"query": query}
        if variables is not None:
            data["variables"] = variables

        data = json.dumps(data, cls=DjangoJSONEncoder)
        app_token = AppToken.objects.get(app=self.app).auth_token
        headers = {
            "content-type": "application/json",
            "Authorization": f'Bearer {app_token}'
        }

        result = requests.post(url=settings.API_URI, data=data, headers=headers)
        return result
