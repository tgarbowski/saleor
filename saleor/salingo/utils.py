def get_sql_function_by_file_name(sql_file_name, function_name):
    header = 'drop function ' + function_name + ';'
    body = ''
    with open('/app/saleor/salingo/sql/' + sql_file_name, 'r', encoding='utf8') as sql_file:
        for line in  sql_file.readlines():
            body = body + line
    return header + body
