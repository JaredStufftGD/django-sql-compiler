import json
import os
import statistics
import time

import django
import pytest
from django.db import connections
from django.db.utils import DatabaseError

from sql_compiler import compose, fetch_rows
from sql_compiler.spike_a import ResultIn

from .spike_models import SpikeBench

pytestmark = pytest.mark.skipif(
    os.environ.get('SQLCOMPILER_SPIKE_BENCH') != '1', reason='GRO-24 spike benchmark: set SQLCOMPILER_SPIKE_BENCH=1'
)

SIZES = (10, 1000, 100000)
RUNS = 5


def install_bench(alias):
    connection = connections[alias]
    with connection.schema_editor() as editor:
        if SpikeBench._meta.db_table in connection.introspection.table_names():
            editor.delete_model(SpikeBench)
        editor.create_model(SpikeBench)
    SpikeBench.objects.using(alias).bulk_create([SpikeBench(id=i, v=i) for i in range(1, 100001)], batch_size=5000)


def uninstall_bench(alias):
    with connections[alias].schema_editor() as editor:
        editor.delete_model(SpikeBench)


def time_method(fn, n):
    runs = []
    for _ in range(RUNS):
        start = time.perf_counter()
        got = fn()
        runs.append(time.perf_counter() - start)
        assert len(got) == n
    return runs


def run_bench(alias, label):
    bench = SpikeBench.objects.using(alias)
    records = []
    for n in SIZES:
        result = compose(
            'SELECT x.id FROM (%(q)s) x WHERE x.id <= %(n)s', q=SpikeBench.objects.using(alias).values('id'), n=n
        )

        def route_a():
            return list(bench.filter(pk__in=ResultIn(result, 'id')).values_list('id', flat=True))

        def fetch_rows_list():
            keys = [row['id'] for row in fetch_rows(result, dict)]
            return list(bench.filter(pk__in=keys).values_list('id', flat=True))

        for method, fn in (('route_a', route_a), ('fetch_rows_list', fetch_rows_list)):
            record = {
                'backend': label,
                'django': django.get_version(),
                'n': n,
                'method': method,
                'median_s': None,
                'error': None,
                'runs_s': [],
            }
            try:
                runs = time_method(fn, n)
                record['runs_s'] = runs
                record['median_s'] = statistics.median(runs)
            except DatabaseError as exc:
                record['error'] = 'error: {}: {}'.format(type(exc).__name__, str(exc).splitlines()[0])
            records.append(record)
    out = os.environ.get('SQLCOMPILER_SPIKE_BENCH_OUT')
    if out:
        with open(out, 'a') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')
    print('\n| backend | django | n | method | median_s | error |')
    print('|---|---|---|---|---|---|')
    for r in records:
        median = '' if r['median_s'] is None else '{:.4f}'.format(r['median_s'])
        print(
            '| {backend} | {django} | {n} | {method} | {m} | {error} |'.format(
                m=median, **{**r, 'error': r['error'] or ''}
            )
        )
    return records


def test_spike_bench_route_a_sqlite(things_sqlite):
    install_bench(things_sqlite)
    try:
        records = run_bench(things_sqlite, 'sqlite')
    finally:
        uninstall_bench(things_sqlite)
    assert all(r['error'] or r['median_s'] is not None for r in records)
    assert len(records) == 6


def test_spike_bench_route_a_default(db_under_test):
    connection = connections['default']
    if connection.vendor != 'postgresql':
        pytest.skip('GRO-24 spike benchmark: the pg3 cell needs PostgreSQL as default')
    connection.ensure_connection()
    if type(connection.connection).__module__.split('.')[0] != 'psycopg':
        pytest.skip('GRO-24 spike benchmark: the pg3 cell needs psycopg 3')
    install_bench('default')
    try:
        records = run_bench('default', 'pg3')
    finally:
        uninstall_bench('default')
    assert len(records) == 6
