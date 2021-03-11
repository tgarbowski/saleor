import os


def read_sql_from_file(sql_file_name):
    body = ''
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, 'sql/' + sql_file_name)
    with open(path, 'r', encoding='utf8') as sql_file:
        for line in sql_file.readlines():
            body = body + line
    return body
