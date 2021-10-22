import json
import string
import random

from django.db import migrations, connection


def generate_key_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))


def get_products_from_db():
    dbCursor = connection.cursor()
    dbCursor.execute("""select id, description from product_product pp""")
    return dbCursor.fetchall()


def get_object_from_json(products):
    return {product[0]: json.loads(product[1]) for product in products}


def generate_new_description_json(products):
    for key, value in products.items():
        try:
            for specification in enumerate(value['blocks']):
                values = list(specification)[1]
                values['key'] = generate_key_id()
                if 'type' not in values:
                    values['type'] = 'unstyled'
                values['depth'] = 0
                values['entityRanges'] = []
                values['inlineStyleRanges'] = []
        except KeyError:
            continue


def update_db_table(description_json, id):

    db_cursor = connection.cursor()
    db_cursor.execute("""update product_product
                set description_json = %s
                where id = %s""", (description_json, id))


def update_description_json(apps, schema_editor):
    products = get_object_from_json(get_products_from_db())
    generate_new_description_json(products)
    for key, value in products.items():
        update_db_table(json.dumps(value), key)




class Migration(migrations.Migration):
    dependencies = [
        ("salingo", "0002_update_prices")
    ]

    operations = [
        migrations.RunPython(update_description_json)
    ]
