# Generated by Django 3.1.2 on 2021-06-17 10:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('warehouse', '0011_auto_20200714_0539'),
        ('wms', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='wmsdocument',
            name='warehouse_second',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='warehouse.warehouse'),
        ),
        migrations.AlterField(
            model_name='wmsdocument',
            name='number',
            field=models.CharField(max_length=255, unique=True),
        ),
        migrations.AlterField(
            model_name='wmsdocument',
            name='status',
            field=models.CharField(choices=[('APPROVED', 'APPROVED'), ('DRAFT', 'DRAFT')], default='DRAFT', max_length=20),
        ),
        migrations.AlterField(
            model_name='wmsdocument',
            name='warehouse',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='warehouse.warehouse'),
        ),
    ]
