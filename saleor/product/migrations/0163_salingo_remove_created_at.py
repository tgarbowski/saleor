# Generated by Django 3.2.12 on 2022-03-31 13:37

from django.db import migrations

from saleor_gs.saleor.salingo.utils import read_sql_from_file


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0162_auto_20220228_1233'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='created_at',
        ),
        migrations.RunSQL(read_sql_from_file('sku_to_date.sql')),
        migrations.RunSQL(
            """
            update product_product pp set created = sku_to_date(sku) + interval '6 hours'
            from product_productvariant pv
            where pp.id = pv.product_id
            """
        )
    ]
