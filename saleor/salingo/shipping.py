from saleor.plugins.inpost.plugin import get_inpost_tracking_number
from saleor.plugins.gls.utils import get_gls_tracking_number
from saleor.order.models import Fulfillment


def update_tracking_number(order, package_id):
    courier = order.shipping_method.metadata.get("courier")
    tracking_number = None

    if courier == 'INPOST':
        tracking_number = get_inpost_tracking_number(package_id=package_id)
    if courier == 'GLS':
        tracking_number = get_gls_tracking_number(package_id=package_id)

    if tracking_number:
        fulfillment = get_fulfillment_by_package_id(order=order, package_id=package_id)
        fulfillment.tracking_number = tracking_number
        fulfillment.save()


def get_fulfillment_by_package_id(order, package_id):
    return Fulfillment.objects.get(order=order, private_metadata__package__id=int(package_id))
