import graphene

from .mutations import ExtMigloCsv, ExtTallyCsv


class CsvMutations(graphene.ObjectType):
    ext_tally_csv = ExtTallyCsv.Field()
    ext_miglo_csv = ExtMigloCsv.Field()
