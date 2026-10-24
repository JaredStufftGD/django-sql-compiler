# Pinned executable_query output, captured from real runs with:
#   Django 6.1.2, psycopg2 2.9.13, PostgreSQL: PostgreSQL 18.6
#   mysqlclient (2, 3, 0, 'final', 0), MySQL: 8.4.13
# These strings are psycopg2/mysqlclient output. Under psycopg 3 the Postgres cases
# xfail (GRO-14) before the comparison, so re-capture when GRO-14 is fixed.
# 'non_ascii', 'non_ascii_cjk', 'non_ascii_emoji' (and MySQL 'non_ascii_euro') hold non-ASCII values, checked by
# test_non_ascii_param_is_not_garbled, the non-ASCII CASES and the MySQL latin1 test.

EXPECTED = {}

POSTGRES_SELECT = 'SELECT "sqlcompiler_thing"."id", "sqlcompiler_thing"."name", "sqlcompiler_thing"."other", "sqlcompiler_thing"."n", "sqlcompiler_thing"."flag", "sqlcompiler_thing"."day", "sqlcompiler_thing"."ts", "sqlcompiler_thing"."dec" FROM "sqlcompiler_thing" '
EXPECTED['postgres'] = {
    'single_quote': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name" = \'it\'\'s\'',
    'backslash': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name" = \'back\\slash\'',
    'percent_literal_param': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name"::text LIKE \'%\\%%\'',
    'percent_empty_params': POSTGRES_SELECT + "WHERE (name LIKE 'plain%')",
    'percent_with_params': POSTGRES_SELECT + 'WHERE ("sqlcompiler_thing"."n" > 0 AND "sqlcompiler_thing"."name"::text LIKE \'%\' || REPLACE(REPLACE(REPLACE(("sqlcompiler_thing"."other"), E\'\\\\\', E\'\\\\\\\\\'), E\'%\', E\'\\\\%\'), E\'_\', E\'\\\\_\') || \'%\')',
    'null': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."n" IS NULL',
    'null_param': POSTGRES_SELECT + 'WHERE (COALESCE(n, -1) = COALESCE(NULL, -1))',
    'int': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."n" = 1',
    'decimal': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."dec" = 1.50',
    'float_param': POSTGRES_SELECT + 'WHERE (n < 2.5)',
    'bool': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."flag"',
    'bool_param': POSTGRES_SELECT + 'WHERE (flag = true)',
    'in_list': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."n" IN (1, 3)',
    'date': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."day" = \'2024-01-02\'::date',
    'datetime': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."ts" = \'2024-01-02T03:04:05+00:00\'::timestamptz',
    'non_ascii': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name" = \'café\'',
    'non_ascii_cjk': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name" = \'東京\'',
    'non_ascii_emoji': POSTGRES_SELECT + 'WHERE "sqlcompiler_thing"."name" = \'😀\'',
}

MYSQL_SELECT = 'SELECT `sqlcompiler_thing`.`id`, `sqlcompiler_thing`.`name`, `sqlcompiler_thing`.`other`, `sqlcompiler_thing`.`n`, `sqlcompiler_thing`.`flag`, `sqlcompiler_thing`.`day`, `sqlcompiler_thing`.`ts`, `sqlcompiler_thing`.`dec` FROM `sqlcompiler_thing` '
EXPECTED['mysql'] = {
    'single_quote': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = 'it\\'s'",
    'backslash': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = 'back\\\\slash'",
    'percent_literal_param': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` LIKE BINARY '%\\\\%%'",
    'percent_empty_params': MYSQL_SELECT + "WHERE (name LIKE 'plain%')",
    'percent_with_params': MYSQL_SELECT + "WHERE (`sqlcompiler_thing`.`n` > 0 AND `sqlcompiler_thing`.`name` LIKE BINARY CONCAT('%', REPLACE(REPLACE(REPLACE((`sqlcompiler_thing`.`other`), '\\\\', '\\\\\\\\'), '%', '\\%'), '_', '\\_'), '%'))",
    'null': MYSQL_SELECT + 'WHERE `sqlcompiler_thing`.`n` IS NULL',
    'null_param': MYSQL_SELECT + 'WHERE (COALESCE(n, -1) = COALESCE(NULL, -1))',
    'int': MYSQL_SELECT + 'WHERE `sqlcompiler_thing`.`n` = 1',
    'decimal': MYSQL_SELECT + 'WHERE `sqlcompiler_thing`.`dec` = 1.50',
    'float_param': MYSQL_SELECT + 'WHERE (n < 2.5e0)',
    'bool': MYSQL_SELECT + 'WHERE `sqlcompiler_thing`.`flag` = 1',
    'bool_param': MYSQL_SELECT + 'WHERE (flag = 1)',
    'in_list': MYSQL_SELECT + 'WHERE `sqlcompiler_thing`.`n` IN (1, 3)',
    'date': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`day` = '2024-01-02'",
    'datetime': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`ts` = '2024-01-02 03:04:05'",
    'non_ascii': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = 'café'",
    'non_ascii_cjk': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = '東京'",
    'non_ascii_emoji': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = '😀'",
    'non_ascii_euro': MYSQL_SELECT + "WHERE `sqlcompiler_thing`.`name` = '€'",
}
