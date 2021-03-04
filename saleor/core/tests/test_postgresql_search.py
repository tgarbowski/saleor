import pytest
from django.utils.text import slugify

from ...account.models import Address
from ...graphql.product.filters import product_search
from ...product.models import Product

PRODUCTS = [
    ("Arabica Coffee", "The best grains in galactic"),
    ("Cool T-Shirt", "Blue and big."),
    ("Roasted chicken", "Fabulous vertebrate"),
]


@pytest.fixture
def named_products(category, product_type):
    def gen_product(name, description):
        product = Product.objects.create(
            name=name,
            slug=slugify(name),
            description=description,
            description_plaintext=description,
            product_type=product_type,
            category=category,
            is_published=True,
        )
        return product

    return [gen_product(name, desc) for name, desc in PRODUCTS]


def execute_search(phrase):
    """Execute product search."""
    return product_search(phrase)


@pytest.mark.parametrize(
    "phrase,product_num",
    [("Arabica", 0), ("chicken", 2), ("blue", 1), ("roast", 2), ("cool", 1)],
)
@pytest.mark.integration
@pytest.mark.django_db
def test_storefront_product_fuzzy_name_search(named_products, phrase, product_num):
    results = execute_search(phrase)
    assert 1 == len(results)
    assert named_products[product_num] in results


def unpublish_product(product):
    prod_to_unpublish = product
    prod_to_unpublish.is_published = False
    prod_to_unpublish.save()


USERS = [
    ("Andreas", "Knop", "adreas.knop@example.com"),
    ("Euzebiusz", "Ziemniak", "euzeb.potato@cebula.pl"),
    ("John", "Doe", "johndoe@example.com"),
]
ORDER_IDS = [10, 45, 13]
ORDERS = [[pk] + list(user) for pk, user in zip(ORDER_IDS, USERS)]


def gen_address_for_user(first_name, last_name):
    return Address.objects.create(
        first_name=first_name,
        last_name=last_name,
        company_name="Mirumee Software",
        street_address_1="Tęczowa 7",
        city="Wrocław",
        postal_code="53-601",
        country="PL",
    )
