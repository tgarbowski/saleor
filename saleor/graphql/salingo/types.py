import graphene


class PaymentUrl(graphene.ObjectType):
    class Meta:
        description = ("data to generate redirect url for payment")

    payment_url = graphene.String(description="")


class WarehousePdfFiles(graphene.ObjectType):
    class Meta:
        description = ("Generated pdf warehouse list and wms docments list files encoded in B64")

    warehouse_list = graphene.String(description="")
    wms_list = graphene.String(description="")
