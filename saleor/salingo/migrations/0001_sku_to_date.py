# Generated by Django 3.1.2 on 2021-03-11 13:06

from django.db import migrations
from ..utils import read_sql_from_file


class Migration(migrations.Migration):
    dependencies = [
    ]

    operations = [
        migrations.RunSQL(read_sql_from_file('sku_to_date.sql')),
        migrations.RunSQL(
            """
            update product_product pp set updated_at  =
            (select sku_to_date(sku) from product_productvariant pv where pp.id = pv.product_id)
            """
        )
    ]
