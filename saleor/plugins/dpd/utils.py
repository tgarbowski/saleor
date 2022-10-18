import base64

from saleor.plugins.inpost.plugin import Shipping
from .api import DpdApi
from zeep.helpers import serialize_object
from saleor.salingo.utils import find_keys
from saleor.salingo.shipping import CarrierError, ShipmentStrategy


class DpdShipment(ShipmentStrategy):
    def create_package(self, shipping, package, fulfillment) -> str:
        return create_dpd_shipment(shipping, package, fulfillment)

    def generate_label(self, package_id) -> str:
        return generate_dpd_label(package_id)

    def get_tracking_number(self, package_id) -> str:
        raise NotImplementedError


def create_dpd_receiver(shipping: Shipping):
    address = shipping.receiver.address.street_address_1
    if shipping.receiver.address.street_address_2:
        address += " " + shipping.receiver.address.street_address_2
    receiver = {
        'city': shipping.receiver.address.city,
        'postalCode': shipping.receiver.address.postal_code,
        'address': address,
        'company': shipping.receiver.address.company_name,
        'countryCode': shipping.receiver.address.country,
        'email': shipping.receiver.email,
        'phone': shipping.receiver.address.phone,
        'name': f'{shipping.receiver.address.first_name} {shipping.receiver.address.last_name}'
    }
    return receiver


def create_dpd_sender(shipping: Shipping, fid: str):
    sender = {
        'city': shipping.sender.city,
        'postalCode': shipping.sender.postal_code,
        'address': shipping.sender.street_address_1,
        'company': shipping.sender.company_name,
        'countryCode': shipping.sender.country,
        # TODO: email
        'email': '',
        'phone': shipping.sender.phone,
        'fid': fid
    }
    return sender


def create_dpd_package(package):
    parcels = []

    for parcel in package:
        p = {
            "weight": parcel.weight,
            "sizeX": parcel.sizeX,
            "sizeY": parcel.sizeY,
            "sizeZ": parcel.sizeZ
        }
        parcels.append(p)

    return parcels


def prepare_package_info_from_dpd_api_response(response_package, package):
    pack = response_package.Packages.Package[0]
    parcels = pack.Parcels.Parcel
    new_parcels = []

    for parcel, response_parcel in zip(package, parcels):
        new_parcels.append(
            {
                "id": response_parcel.ParcelId,
                "waybill": response_parcel.Waybill,
                "weight": parcel['weight'],
                "sizeX": parcel['sizeX'],
                "sizeY": parcel['sizeY'],
                "sizeZ": parcel['sizeZ']
            }
        )

    json_package = {
        "status": pack.Status,
        "id": pack.PackageId,
        "parcels": new_parcels,
    }
    return json_package


def save_package_data_to_fulfillment(fulfillment, json_package, tracking_number):
    fulfillment.store_value_in_private_metadata({'package': json_package})
    fulfillment.tracking_number = tracking_number
    fulfillment.save()


def create_dpd_shipment(shipping: Shipping, package, fulfillment):
    dpd_api = DpdApi()

    receiver = create_dpd_receiver(shipping=shipping)
    sender = create_dpd_sender(shipping=shipping, fid=dpd_api.API_FID)
    package_data = create_dpd_package(package=package)

    response_package = dpd_api.generate_package_shipment(
        packageData=package_data,
        receiverData=receiver,
        senderData=sender
    )

    if response_package.Status != 'OK':
        package_errors = get_dpd_response_errors(response_package, key='Info')
        raise CarrierError(message=package_errors)

    json_package = prepare_package_info_from_dpd_api_response(
        response_package=response_package,
        package=package
    )

    try:
        waybill = response_package.Packages.Package[0].Parcels.Parcel[0].Waybill
    except:
        waybill = response_package.Packages.Package[0].PackageId

    save_package_data_to_fulfillment(
        fulfillment=fulfillment,
        json_package=json_package,
        tracking_number=waybill
    )
    package_id = response_package.Packages.Package[0].PackageId
    return package_id


def generate_dpd_label(package_id: str):
    api = DpdApi()
    label = api.generate_label(
        packageId=package_id
    )
    label_data = label.documentData
    if label_data is None:
        label_errors = get_dpd_response_errors(label, key='status')
        raise CarrierError(message=label_errors)

    label_b64 = base64.b64encode(label_data).decode('ascii')
    return label_b64


def get_dpd_response_errors(response, key) -> str:
    try:
        dict_response = serialize_object(response, target_cls=dict)
        errors = list(find_keys(dict_response, key))
        error = errors[0]
    except:
        error = ''
    return error
