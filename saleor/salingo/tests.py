from decimal import Decimal

from measurement.measures import Weight
from pytest import approx

from saleor.salingo.business_rules import Executors


def test_calculate_price_weight_mode():
    validated_pricing_variables = Executors.get_validated_pricing_variables(
        current_price=Decimal(1.00),
        weight=Weight(kg=2),
        result='k12.40'
    )

    price = Executors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(24.80))


def test_calculate_price_weight_null():
    validated_pricing_variables = Executors.get_validated_pricing_variables(
        current_price=Decimal(1.00),
        weight=None,
        result='k12.40'
    )

    assert validated_pricing_variables is None


def test_calculate_price_discount_mode():
    validated_pricing_variables = Executors.get_validated_pricing_variables(
        current_price=Decimal(10.00),
        weight=Weight(kg=2),
        result='d10'
    )

    price = Executors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(9.00))


def test_calculate_price_item_mode():
    validated_pricing_variables = Executors.get_validated_pricing_variables(
        current_price=Decimal(25.99),
        weight=Weight(kg=2),
        result='i25.99'
    )

    price = Executors.calculate_price(validated_pricing_variables)

    assert price == approx(Decimal(25.99))

