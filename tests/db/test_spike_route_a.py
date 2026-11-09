from . import spike_a_cases as cases


def test_route_a_q1_params_default(db_under_test, spike_default):
    cases.check_q1_params('default')


def test_route_a_q2_same_alias_default(db_under_test, spike_default):
    cases.check_q2_same_alias('default')


def test_route_a_q3_percent_default(db_under_test, spike_default):
    cases.check_q3_percent('default')


def test_route_a_q4_lazy_default(db_under_test, spike_default):
    cases.check_q4_lazy('default')


def test_route_a_q6_roundtrip_default(db_under_test, spike_default):
    cases.check_q6_roundtrip('default')


def test_route_a_q6_executable_query_default(db_under_test, spike_default):
    cases.check_q6_executable_query('default')


def test_route_a_q7_clone_default(db_under_test, spike_default):
    cases.check_q7_clone('default')


def test_route_a_q2_mismatch_default_result_on_sqlite_live(db_under_test, spike_default, spike_sqlite):
    cases.check_q2_mismatch('default', 'sqlite_live')


def test_route_a_q2_mismatch_sqlite_live_result_on_default(db_under_test, spike_default, spike_sqlite):
    cases.check_q2_mismatch('sqlite_live', 'default')


def test_route_a_q2_hazard_rawsql_no_alias_check_default(db_under_test, spike_default, spike_sqlite):
    cases.check_q2_hazard_rawsql_no_alias_check('default', 'sqlite_live')


def test_route_a_a_in_exists_join_default(db_under_test, spike_default):
    cases.check_a_in_exists_join('default')


def test_route_a_a_null_default(db_under_test, spike_default):
    cases.check_a_null('default')


def test_route_a_a_null_hazard_not_in_default(db_under_test, spike_default):
    cases.check_a_null_hazard_not_in('default')


def test_route_a_a_composite_default(db_under_test, spike_default):
    cases.check_a_composite('default')


def test_route_a_a_composite_row_value_default(db_under_test, spike_default):
    cases.check_a_composite_row_value('default')


def test_route_a_a_keytypes_default(db_under_test, spike_default):
    cases.check_a_keytypes('default')


def test_route_a_a_keytypes_hazard_uuid_params_default(db_under_test, spike_default):
    cases.check_a_keytypes_hazard_uuid_params('default')


def test_route_a_a_duplicates_default(db_under_test, spike_default):
    cases.check_a_duplicates('default')


def test_route_a_a_duplicates_hazard_join_default(db_under_test, spike_default):
    cases.check_a_duplicates_hazard_join('default')


def test_route_a_a_mysql_limit_default(db_under_test, spike_default):
    cases.check_a_mysql_limit('default')


def test_route_a_a_mysql_limit_hazard_rawsql_default(db_under_test, spike_default):
    cases.check_a_mysql_limit_hazard_rawsql('default')
