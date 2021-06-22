import graphene


class WMSDocumentStatusFilter(graphene.Enum):
    APPROVED = "APPROVED"
    DRAFT = "DRAFT"


class WMSDocumentTypeFilter(graphene.Enum):
    GRN = "GRN"
    GIN = "GIN"
    IWM = "IWM"
    FGTN = "FGTN"
    IO = "IO"
