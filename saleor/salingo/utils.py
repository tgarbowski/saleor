import asyncio
import functools
import os
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse

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


def remover_auth(func):
    @functools.wraps(func)
    def wrapper_auth(*args, **kwargs):
        if args[0].headers.get('X-API-KEY') != settings.REMOVER_SALEOR_API_KEY:
            return HttpResponse(status=403)
        return func(*args, **kwargs)
    return wrapper_auth


def date_x_days_before(days: int):
    return date.today() - timedelta(days=days)


def datetime_x_days_before(days: int):
    return datetime.now() - timedelta(days=days)


def email_dict_errors(errors):
    from django.core.mail import send_mail
    from saleor.plugins.allegro.utils import prepare_failed_tasks_email
    from django.utils.html import strip_tags

    msg = prepare_failed_tasks_email(errors)
    plain_message = strip_tags(msg)

    send_mail(
        subject='',
        message=plain_message,
        from_email='',
        recipient_list=[''],
        html_message=msg
    )
