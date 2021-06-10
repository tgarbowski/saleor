import graphene

from saleor.graphql.wms.types.documents import WMSDocument, WMSDocPosition

from saleor.graphql.core.fields import FilterInputConnectionField

from saleor.graphql.wms.filters import WMSDocumentFilterInput

from saleor.graphql.wms.resolvers import resolve_wms_documents


class WMSDocumentQueries(graphene.ObjectType):
    wms_documents = FilterInputConnectionField(
        WMSDocument,
        filter=WMSDocumentFilterInput(description="Filtering wms documents"),
        description="List of wms documents"
    )

    def resolve_wms_documents(self, info, **kwargs):
        return resolve_wms_documents(info, kwargs)
