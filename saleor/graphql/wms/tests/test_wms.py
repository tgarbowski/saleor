MUTATION_CREATE_WMSDOCUMENT = """
mutation WMSDocumentCreate($input: WMSDocumentCreateInput!) {
    wmsdocumentCreate(input: $input){
        wMSDocument {
            documentType
            number
            status
            warehouse {
                id
            }
        }
    }
}
"""

MUTATION_UPDATE_WMSDOCUMENT = """
mutation WMSDocumentUpdate($id: ID!, $input: WMSInput!) {
    wmsdocumentUpdate(id: $id, input: $input){
        wMSDocument {
            documentType
            number
            status
            warehouse {
                id
            }
        }
    }
}
"""

MUTATION_CREATE_WMSDOCPOSITION = """
mutation WMSDocPositionCreate($input: WMSDocPositionCreateInput!) {
    wmsdocpositionCreate(input: $input){
        wMSDocPosition {
            quantity
            weight
            productVariant {
                id
            }
            document {
                id
            }
        }
    }
}
"""


MUTATION_UPDATE_WMSDOCPOSITION = """
mutation WMSDocPositionUpdate($id: ID!, $input: WMSDocPositionInput!) {
    wmsdocpositionUpdate(id: $id, input: $input){
        wMSDocPosition {
            quantity
            weight
            productVariant {
                id
            }
            document {
                id
            }
        }
    }
}
"""
