from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.inpost.plugin import Shipping
from .api import DpdApi


def get_dpd_config():
    manager = get_plugins_manager()
    dpd_config = manager.get_plugin('Dpd').config

    return dpd_config


def get_dpd_fid():
    dpd_config = get_dpd_config()
    return dpd_config.master_fid


def create_dpd_receiver(shipping: Shipping):
    receiver = {
        'city': shipping.receiver.address.city,
        'postalCode': shipping.receiver.address.postal_code,
        'address': shipping.receiver.address.street_address_1,
        'company': shipping.receiver.address.company_name,
        'countryCode': shipping.receiver.address.country,
        'email': shipping.receiver.email,
        'phone': shipping.receiver.address.phone
    }
    return receiver


def create_dpd_sender(shipping: Shipping):
    receiver = {
        'city': shipping.sender.city,
        'postalCode': shipping.sender.postal_code,
        'address': shipping.sender.street_address_1,
        'company': shipping.sender.company_name,
        'countryCode': shipping.sender.country,
        # TODO: email
        'email': '',
        'phone': shipping.sender.phone,
        'fid': get_dpd_fid()
    }
    return receiver

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


def create_dpd_shipment(shipping: Shipping, package):
    receiver = create_dpd_receiver(shipping=shipping)
    sender = create_dpd_sender(shipping=shipping)
    package_data = create_dpd_package(package=package)

    dpd_api = DpdApi()

    package = dpd_api.generate_package_shipment(
        packageData=package_data,
        receiverData=receiver,
        senderData=sender,
        #servicesData=data['input'].get('services')
    )
    '''
    if package.Status != 'OK':
        return DpdPackageCreate(
            status=package.Status
        )
    '''
    package = package.Packages.Package[0]
    parcels = package.Parcels.Parcel
    parcel_ids = [parcel.ParcelId for parcel in package.Parcels.Parcel]
    waybills = [parcel.Waybill for parcel in package.Parcels.Parcel]
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
        "status": package.Status,
        "id": package.PackageId,
        "parcels": new_parcels,
    }

    fulfillment_id = data['input']['fulfillment']
    fulfillment = graphene.Node.get_node_from_global_id(info, fulfillment_id, Fulfillment)
    fulfillment.store_value_in_private_metadata({'package': json_package})
    fulfillment.tracking_number = package.PackageId
    fulfillment.save()
