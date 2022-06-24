import graphene


class PaymentUrl(graphene.ObjectType):
    class Meta:
        description = ("data to generate redirect url for payment")

    payment_url = graphene.String(description="")
