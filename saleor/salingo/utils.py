import asyncio
import os
from datetime import date, datetime

from django.core.exceptions import ValidationError

from aiohttp.client import ClientSession


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


async def patch_async(objs):
    MAX_TASKS = 20
    MAX_TIME = 1000
    tasks = []
    sem = asyncio.Semaphore(MAX_TASKS)

    async with ClientSession() as sess:
        for obj in objs:
            tasks.append(
                asyncio.wait_for(
                    patch_one(obj, sess, sem),
                    timeout=MAX_TIME,
                )
            )

        return await asyncio.gather(*tasks)


async def patch_one(obj, sess, sem):
    async with sem:
        async with sess.patch(url=obj['url'], json=obj['payload'], headers=obj['headers']) as res:
            if res.status != 200:
                return obj
