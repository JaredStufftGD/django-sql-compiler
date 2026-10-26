from .expected import EXPECTED, POSTGRES_PSYCOPG3_OVERRIDES


def test_psycopg3_overrides_differ_from_psycopg2():
    for key, value in POSTGRES_PSYCOPG3_OVERRIDES.items():
        assert key in EXPECTED['postgres'], key
        assert value != EXPECTED['postgres'][key], key


def test_psycopg3_dict_covers_every_postgres_key():
    assert set(EXPECTED['postgres_psycopg3']) == set(EXPECTED['postgres'])
