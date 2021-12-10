import os
from datetime import date, datetime

from django.core.exceptions import ValidationError


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
    date = '%Y-%m-%d'
