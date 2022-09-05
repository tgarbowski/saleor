from datetime import datetime

import boto3
from botocore.client import ClientError

from django.core.management.base import BaseCommand, CommandError

from saleor.salingo.remover import RemoverApi, get_media_to_remove


class Command(BaseCommand):
    version = "1.0"

    def add_arguments(self, parser):
        parser.add_argument('--start_date', type=str, help='product creation start date')
        parser.add_argument('--end_date', type=str, help='product creation end date')
        parser.add_argument('--source', type=str, help='s3 source bucket')
        parser.add_argument('--target', type=str, help='s3 target bucket')
        parser.add_argument('--backup', type=str, help='s3 backup bucket')
        parser.add_argument('--mode', type=str, help='processing mode')

    def handle(self, *args, **options):
        self.start_date = options['start_date']
        self.end_date = options['end_date']
        self.source = options['source']
        self.target = options['target']
        self.backup = options['backup']
        self.mode = options['mode']

        self.validate_dates()

        if self.mode == 'backup':
            self.handle_backup_flow()
        elif self.mode == 'migration':
            self.handle_migration_flow()

    def handle_backup_flow(self):
        self.validate_bucket(self.backup)

        RemoverApi.process_images_backup_mode(
            source=self.source,
            target=self.target,
            backup=self.backup,
            images=get_media_to_remove(self.start_date, self.end_date)
        )

    def handle_migration_flow(self):
        RemoverApi.process_images_migration_mode(
            source=self.source,
            target=self.target,
            images=get_media_to_remove(self.start_date, self.end_date)
        )

    def validate_bucket(self, bucket):
        s3 = boto3.resource('s3')

        try:
            s3.meta.client.head_bucket(Bucket=bucket)
        except ClientError:
            raise CommandError(
                "Wrong backup bucket name. "
            )

    def validate_dates(self):
        if not self.start_date:
            raise CommandError(
                "Unknown start date. "
                "Use `--start_date` flag "
                "eg. --start_date '2021-08-17'"
            )
        if not self.end_date:
            raise CommandError(
                "Unknown end_date date. "
                "Use `--end_date` flag "
                "eg. --end_date '2021-08-17'"
            )

        try:
            start_date = datetime.strptime(self.start_date, "%Y-%m-%d")
        except ValueError:
            raise CommandError(
                "Wrong end date. "
                "`--end_date` flag should be in format eg. `2021-08-17`"
            )

        try:
            end_date = datetime.strptime(self.end_date, "%Y-%m-%d")
        except ValueError:
            raise CommandError(
                "Wrong end date. "
                "`--end_date` flag should be in format eg. `2021-08-17`"
            )

        if start_date > end_date:
            raise CommandError(
                "Provided start date is greater than end date."
            )
