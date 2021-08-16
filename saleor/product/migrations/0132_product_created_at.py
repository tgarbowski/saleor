# Generated by Django 3.1.2 on 2021-08-16 10:44

from django.db import migrations, models

from saleor.salingo.utils import read_sql_from_file


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0131_update_ts_vector_existing_product_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.RunSQL(read_sql_from_file('sku_to_date.sql')),
        migrations.RunSQL(
            """
            update product_product pp set updated_at = sku_to_date(sku) + interval '6 hours'
            from product_productvariant pv
            where pp.id = pv.product_id
            """
        ),
        migrations.RunSQL(
            """
            update product_product set created_at = updated_at
            """
        )
    ]
