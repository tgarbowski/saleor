import graphene

from .mutations.wms import WMSDocumentCreate, WMSDocumentUpdate, WMSDocPositionCreate, WMSDocPositionUpdate

from ...wms.models import WMSDocument

from saleor.graphql.core.fields import FilterInputConnectionField

from ...wms.filters import WMSDocumentFilterInput

from ...wms.resolvers import resolve_wms_documents


class WMSDocumentMutations(graphene.ObjectType):
    # Documents
    wmsdocument_create = WMSDocumentCreate.Field()
    wmsdocument_update = WMSDocumentUpdate.Field()
    # Documents positions
    wmsdocposition_create = WMSDocPositionCreate.Field()
    wmsdocposition_update = WMSDocPositionUpdate.Field()


class WMSDocumentQueries(graphene.ObjectType):
    wms_documents = FilterInputConnectionField(
        WMSDocument,
        filter=WMSDocumentFilterInput(description="Filtering wms documents"),
        description="List of wms documents"
    )

    def resolve_wms_documents(self, info, **kwargs):
        return resolve_wms_documents(info, kwargs)
