from saleor.plugins.manager import get_plugins_manager

from dpd_info_client_api.api import DPDAPI as BaseDpdApi
from dpd_info_client_api.settings import DPDSettingsObject


class DpdApi(BaseDpdApi):
    def GeneratePackageShipment(self,
        packageData,
        recieverData,
        senderData,
        servicesData=None,
        reference=None,
        thirdPartyFID=None,
        langCode='PL'
    ):

        openUMLFeV3 = self['openUMLFeV3']
        packageOpenUMLFeV3 = self['packageOpenUMLFeV3']
        packageOpenUMLFeV3.parcels = [self.getPackagePayload(**package) for package in packageData]
        packageOpenUMLFeV3.receiver = self.getAdressPayload(**recieverData)
        packageOpenUMLFeV3.sender = self.getAdressPayload(**senderData)
        if servicesData:
            packageOpenUMLFeV3.services = self.getServicesPayload(**servicesData)
        packageOpenUMLFeV3.payerType = self.get_from_factory(
            'payerTypeEnumOpenUMLFeV1')('SENDER')

        reference and setattr(packageOpenUMLFeV3, 'reference', reference)
        thirdPartyFID and setattr(packageOpenUMLFeV3, 'thirdPartyFID', thirdPartyFID)

        openUMLFeV3.packages.append(packageOpenUMLFeV3)

        return self.generatePackagesNumbersV4(
            openUMLFeV3, self.generationPolicyPayload,
            langCode, self.authPayload
        )

    def generateProtocol(self,
        senderData,
        waybills=None,
        packages=None,
        sessionType='DOMESTIC',
    ):

        dpdServicesParamsPayload = self['dpdServicesParamsV1']
        dpdServicesParamsPayload.policy = self.generationPolicyPayload
        dpdServicesParamsPayload.pickupAddress = self.getAdressPayload(**senderData)

        SESSION_TYPES = ['DOMESTIC', 'INTERNATIONAL']
        if sessionType not in SESSION_TYPES:
            raise ValueError(
                'sessionType should be one of: %s' % ",".join(SESSION_TYPES))

        sessionPayload = self['sessionDSPV1']
        sessionPayload.sessionType = self.get_from_factory('sessionTypeDSPEnumV1')(
            sessionType)

        if waybills:
            packagePayload = self['packageDSPV1']
            for waybill in waybills:
                parcelPayload = self['parcelDSPV1']
                parcelPayload.waybill = waybill
                packagePayload.parcels.append(parcelPayload)

        if packages:
            packagePayload = []
            for package in packages:
                single_package = self['packageDSPV1']
                single_package.packageId = package
                packagePayload.append(single_package)

        sessionPayload.packages = packagePayload
        dpdServicesParamsPayload.session = sessionPayload

        outputDocFormatDSPEnumPayload = self.get_from_factory(
            'outputDocFormatDSPEnumV1')('PDF')

        outputDocPageFormatDSPEnumPayload = self.get_from_factory(
            'outputDocPageFormatDSPEnumV1')('LBL_PRINTER')

        return self.generateProtocolV2(
            dpdServicesParamsPayload,
            outputDocFormatDSPEnumPayload,
            outputDocPageFormatDSPEnumPayload,
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

