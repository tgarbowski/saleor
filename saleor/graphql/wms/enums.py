import graphene


class WmsDocumentStatusFilter(graphene.Enum):
    APPROVED = "APPROVED"
    DRAFT = "DRAFT"


class WmsDocumentTypeFilter(graphene.Enum):
    GRN = "GRN"
    GIN = "GIN"
    IWM = "IWM"
    FGTN = "FGTN"
    IO = "IO"
