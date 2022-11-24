import graphene

from .mutations import LabelCreate, PackageCreate


class ShippingMutations(graphene.ObjectType):
    package_create = PackageCreate.Field()
    label_create = LabelCreate.Field()
