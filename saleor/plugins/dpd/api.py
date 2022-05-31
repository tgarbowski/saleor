import enum

import zeep

from saleor.plugins.manager import get_plugins_manager


class GenerationPolicy(enum.Enum):
    STOP_ON_FIRST_ERROR = 'STOP_ON_FIRST_ERROR'
    IGNORE_ERRORS = 'IGNORE_ERRORS'
    ALL_OR_NOTHING = 'ALL_OR_NOTHING'


class DpdApi():
    client = None
    service = None
    factory = None

    def __init__(self):
        self.set_config()
        self.init_zeep()

    def set_config(self):
        dpd_config = get_dpd_config()
        self.API_USERNAME = dpd_config.username
        self.API_PASSWORD = dpd_config.password
        self.API_FID = dpd_config.master_fid
        self.API_URL = dpd_config.api_url
        self.generation_policy = 'ALL_OR_NOTHING'

    def init_zeep(self):
        self.client = zeep.Client(self.API_URL)
        self.factory = self.client.type_factory('ns0')

        self.s = self.client.service
        self.service = self.s
        self.__attach_service_refs()

    def __getitem__(self, key):
        return self.get_from_factory(key)()

    @property
    def generation_policy_payload(self):
        return self.get_from_factory('pkgNumsGenerationPolicyV1')(self.generation_policy)

    def __attach_service_refs(self):
        for service_name in self.service.__dir__():
            # skip magic
            if service_name.startswith('__'):
                continue

            service_method = self.service_get(service_name)

            # double check
            if type(service_method) is zeep.proxy.OperationProxy:
                setattr(self, service_name, service_method)

    def get_from_factory(self, object_type):
        if not type(object_type) is type(str('')):
            raise TypeError('Object type is required to be string')

        assert self.factory, "Type Factory is unavaliable, please provide valid settings via .set_config(settings) and run .init_zeep() on instance"

        return getattr(self.factory, object_type)

    def service_get(self, method):
        assert self.s, "Service is unavaliable, please provide valid settings via .set_config(settings) and run .init_zeep() on instance"

        service_method = getattr(self.s, method, None)

        if not service_method:
            raise ('Service does not provide the %s method' % method)

        return service_method

    @property
    def auth_payload(self):
        payload = self['authDataV1']
        payload.login = self.API_USERNAME
        payload.password = self.API_PASSWORD
        payload.masterFid = self.API_FID
        return payload

    def get_package_payload(self, **kwargs):
        payload = self['parcelOpenUMLFeV1']

        for k, v in kwargs.items():
            setattr(payload, k, v)

        return payload

    def get_adress_payload(self, **kwargs):
        payload = self['packageAddressOpenUMLFeV1']

        # fix postal code
        if 'postalCode' in kwargs and '-' in kwargs['postalCode']:
            kwargs['postalCode'] = kwargs['postalCode'].replace('-', '')

        for k, v in kwargs.items():
            setattr(payload, k, v)

        return payload

    def get_services_payload(self, dox=False):
        payload = self['servicesOpenUMLFeV4']

        if dox:
            payload.dox = self['servicePalletOpenUMLFeV1']

        return payload

    def generate_package_shipment(self,
        packageData,
        receiverData,
        senderData,
        servicesData=None,
        reference=None,
        thirdPartyFID=None,
        langCode='PL'
    ):

        self.generation_policy = GenerationPolicy.ALL_OR_NOTHING.value
        openUMLFeV3 = self['openUMLFeV3']
        packageOpenUMLFeV3 = self['packageOpenUMLFeV3']
        packageOpenUMLFeV3.parcels = [self.get_package_payload(**package) for package in packageData]
        packageOpenUMLFeV3.receiver = self.get_adress_payload(**receiverData)
        packageOpenUMLFeV3.sender = self.get_adress_payload(**senderData)
        if servicesData:
            packageOpenUMLFeV3.services = self.get_services_payload(**servicesData)
        packageOpenUMLFeV3.payerType = self.get_from_factory(
            'payerTypeEnumOpenUMLFeV1')('SENDER')

        reference and setattr(packageOpenUMLFeV3, 'reference', reference)
        thirdPartyFID and setattr(packageOpenUMLFeV3, 'thirdPartyFID', thirdPartyFID)

        openUMLFeV3.packages.append(packageOpenUMLFeV3)

        return self.generatePackagesNumbersV4(
            openUMLFeV3, self.generation_policy_payload,
            langCode, self.auth_payload
        )

    def generate_label(self,
        packageId,
        reference=None
    ):

        self.generation_policy = GenerationPolicy.STOP_ON_FIRST_ERROR.value
        dpdServicesParamsPayload = self['dpdServicesParamsV1']
        dpdServicesParamsPayload.policy = self.generation_policy_payload

        sessionPayload = self['sessionDSPV1']
        sessionPayload.sessionType = self.get_from_factory('sessionTypeDSPEnumV1')(
            'DOMESTIC')

        packagePayload = self['packageDSPV1']
        packageId and setattr(packagePayload, 'packageId', packageId)
        reference and setattr(packagePayload, 'reference', reference)

        sessionPayload.packages = packagePayload
        dpdServicesParamsPayload.session = sessionPayload

        outputDocFormatDSPEnumPayload = self.get_from_factory(
            'outputDocFormatDSPEnumV1')('ZPL')

        outputDocPageFormatDSPEnumPayload = self.get_from_factory(
            'outputDocPageFormatDSPEnumV1')('LBL_PRINTER')

        outputLabelTypePayload = self.get_from_factory('outputLabelTypeEnumV1')(
            'BIC3')

        labelVariant = None

        return self.generateSpedLabelsV4(
            dpdServicesParamsPayload,
            outputDocFormatDSPEnumPayload,
            outputDocPageFormatDSPEnumPayload,
            outputLabelTypePayload,
            labelVariant,
            self.auth_payload
        )

    def generate_protocol(self,
        senderData,
        waybills=None,
        packages=None
    ):

        self.generation_policy = GenerationPolicy.STOP_ON_FIRST_ERROR.value
        dpdServicesParamsPayload = self['dpdServicesParamsV1']
        dpdServicesParamsPayload.policy = self.generation_policy_payload
        dpdServicesParamsPayload.pickupAddress = self.get_adress_payload(**senderData)

        sessionPayload = self['sessionDSPV1']
        sessionPayload.sessionType = self.get_from_factory('sessionTypeDSPEnumV1')('DOMESTIC')

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
            self.auth_payload
        )


def get_dpd_config():
    manager = get_plugins_manager()
    config = manager.get_plugin(plugin_id='Dpd').config
    return config
