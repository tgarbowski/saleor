import asyncio
import os
from datetime import date, datetime

from django.core.exceptions import ValidationError

from aiohttp.client import ClientSession
import boto3


def read_sql_from_file(sql_file_name):
    body = ''
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, 'sql/' + sql_file_name)
    with open(path, 'r', encoding='utf8') as sql_file:
        for line in sql_file.readlines():
            body = body + line
    return body


def validate_datetime_string(datetime_string, date_time_format):
    try:
        starting_at = datetime.strptime(datetime_string, date_time_format)
    except:
        raise ValidationError("Wrong date format.")
    if type(starting_at) is not datetime:
        raise ValidationError("Date not provided.")


def validate_date_string(date_string, date_format):
    try:
        starting_at = datetime.strptime(date_string, date_format).date()
    except:
        raise ValidationError("Wrong date format.")
    if type(starting_at) is not date:
        raise ValidationError("Date not provided.")


class SalingoDatetimeFormats:
    datetime = '%Y-%m-%d %H:%M'
    datetime_with_seconds = '%Y-%m-%d %H:%M:%S'
    date = '%Y-%m-%d'


class TooManyRequestsException(Exception):
    def __init__(self, message):
        self.message = message


async def patch_async(objs):
    MAX_TASKS = 20
    tasks = []
    sem = asyncio.Semaphore(MAX_TASKS)

    async with ClientSession() as sess:
        for obj in objs:
            tasks.append(
                asyncio.create_task(patch_one(obj, sess, sem))
            )
        try:
            await asyncio.gather(*tasks)
        except TooManyRequestsException as e:
            for t in tasks:
                t.cancel()
            return e.message


async def patch_one(obj, sess, sem):
    async with sem:
        async with sess.patch(url=obj['url'], json=obj['payload'], headers=obj['headers']) as res:
            if res.status == 429:
                raise TooManyRequestsException(
                    message=obj['url']
                )


def get_aws_secret(secret_id: str) -> str:
    client = boto3.client('secretsmanager', region_name='eu-central-1')
    response = client.get_secret_value(
        SecretId=secret_id,
    )
    return response.get('SecretString')
