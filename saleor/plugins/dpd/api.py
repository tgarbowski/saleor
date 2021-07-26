from saleor.plugins.manager import get_plugins_manager

from dpd_info_client_api.api import DPDAPI as BaseDpdApi
from dpd_info_client_api.settings import DPDSettingsObject
import dpd_info_client_api


class DpdApi(BaseDpdApi):

    def getPickupPackagesParams(self, **kwargs):
        '''
        ns0:pickupPackagesParamsDPPV1(
            dox: xsd:boolean,
            doxCount: xsd:int,
            pallet: xsd:boolean,
            palletMaxHeight: xsd:double,
            palletMaxWeight: xsd:double,
            palletsCount: xsd:int,
            palletsWeight: xsd:double,
            parcelMaxDepth: xsd:double,
            parcelMaxHeight: xsd:double,
            parcelMaxWeight: xsd:double,
            parcelMaxWidth: xsd:double,
            parcelsCount: xsd:int,
            parcelsWeight: xsd:double,
            standardParcel: xsd:boolean
        )
        '''
        packagesParams = self['pickupPackagesParamsDPPV1']

        for k, v in kwargs.items():
            setattr(packagesParams, k, v)

        return packagesParams

    def getPickupCustomer(self, **kwargs):
        # ns0:pickupCustomerDPPV1(customerFullName: xsd:string, customerName: xsd:string, customerPhone: xsd:string)
        pickupCustomer = self['pickupCustomerDPPV1']
        for k, v in kwargs.items():
            setattr(pickupCustomer, k, v)

        return pickupCustomer

    def getPickupPayer(self, **kwargs):
        '''ns0:pickupPayerDPPV1(payerCostCenter: xsd:string, payerName: xsd:string, payerNumber: xsd:int)'''
        pickupPayer = self['pickupPayerDPPV1']

        for k, v in kwargs.items():
            setattr(pickupPayer, k, v)

        return pickupPayer

    def getPickupSender(self, **kwargs):
        '''
        ns0:pickupSenderDPPV1(
            senderAddress: xsd:string,
            senderCity: xsd:string,
            senderFullName: xsd:string,
            senderName: xsd:string,
            senderPhone: xsd:string,
            senderPostalCode: xsd:string
        )'''
        pickupSender = self['pickupSenderDPPV1']

        for k, v in kwargs.items():
            setattr(pickupSender, k, v)

        return pickupSender

    def getpickupCallSimplifiedDetails(self, packagesParams_data, pickupCustomer,
                                       pickupPayer, pickupSender_data):
        '''
        ns0:pickupCallSimplifiedDetailsDPPV1(
            packagesParams: ns0:pickupPackagesParamsDPPV1,
            pickupCustomer: ns0:pickupCustomerDPPV1,
            pickupPayer: ns0:pickupPayerDPPV1,
            pickupSender: ns0:pickupSenderDPPV1)
        '''
        pickupCallSimplifiedDetails = self['pickupCallSimplifiedDetailsDPPV1']

        packagesParams = self.getPickupPackagesParams(**packagesParams_data)
        pickupCustomer = self.getPickupCustomer(**pickupCustomer)
        pickupPayer = self.getPickupPayer(**pickupPayer)
        pickupSender = self.getPickupSender(**pickupSender_data)
        # Merge objects
        pickupCallSimplifiedDetails.packagesParams = packagesParams
        pickupCallSimplifiedDetails.pickupCustomer = pickupCustomer
        pickupCallSimplifiedDetails.pickupPayer = pickupPayer
        pickupCallSimplifiedDetails.pickupSender = pickupSender

        return pickupCallSimplifiedDetails

    def pickupCall(self,
                   packagesParams_data,
                   pickupCustomer_data,
                   pickupPayer_data,
                   pickupSender_data,
                   pickupDate,
                   pickupTimeFrom,
                   pickupTimeTo,
                   senderData=None,
                   returnPayload=False,
                   operationType='INSERT',
                   orderType='DOMESTIC'
                   ):

        '''
            <xs:complexType name="dpdPickupCallParamsV3">
            <xs:sequence>
            <xs:element name="checkSum" type="xs:int" minOccurs="0"/>
            <xs:element name="operationType" type="tns:pickupCallOperationTypeDPPEnumV1" minOccurs="0"/>
            <xs:element name="orderNumber" type="xs:string" minOccurs="0"/>
            <xs:element name="orderType" type="tns:pickupCallOrderTypeDPPEnumV1" minOccurs="0"/>
            <xs:element name="pickupCallSimplifiedDetails" type="tns:pickupCallSimplifiedDetailsDPPV1" minOccurs="0"/>
            <xs:element name="pickupDate" type="xs:string" minOccurs="0"/>
            <xs:element name="pickupTimeFrom" type="xs:string" minOccurs="0"/>
            <xs:element name="pickupTimeTo" type="xs:string" minOccurs="0"/>
            <xs:element name="updateMode" type="tns:pickupCallUpdateModeDPPEnumV1" minOccurs="0"/>
            <xs:element name="waybillsReady" type="xs:boolean" minOccurs="0"/>
            </xs:sequence>
            </xs:complexType>
        '''
        # ns0:packagesPickupCallV4(dpdPickupParamsV3: ns0:dpdPickupCallParamsV3, authDataV1: ns0:authDataV1)
        # Pickup call params payload
        dpdPickupCallParamsPayload = self['dpdPickupCallParamsV3']
        dpdPickupCallParamsPayload.operationType = operationType
        dpdPickupCallParamsPayload.orderType = orderType
        dpdPickupCallParamsPayload.pickupDate = pickupDate
        dpdPickupCallParamsPayload.pickupTimeFrom = pickupTimeFrom
        dpdPickupCallParamsPayload.pickupTimeTo = pickupTimeTo
        dpdPickupCallParamsPayload.waybillsReady = False
        # Pickup call simplified details
        pickupCallSimplifiedDetails = self.getpickupCallSimplifiedDetails(
            packagesParams_data=packagesParams_data,
            pickupCustomer=pickupCustomer_data,
            pickupPayer=pickupPayer_data,
            pickupSender_data=pickupSender_data
        )
        dpdPickupCallParamsPayload.pickupCallSimplifiedDetails = pickupCallSimplifiedDetails

        return self.packagesPickupCallV4(
            dpdPickupCallParamsPayload,
            self.authPayload
        )


def dpd_init():
    manager = get_plugins_manager()
    plugin = manager.get_plugin('Dpd')
    DPDApiSettings = DPDSettingsObject()
    DPDApiSettings.DPD_API_SANDBOX_USERNAME = plugin.config.username
    DPDApiSettings.DPD_API_SANDBOX_PASSWORD = plugin.config.password
    DPDApiSettings.DPD_API_SANDBOX_FID = plugin.config.master_fid

    return DPDApiSettings

