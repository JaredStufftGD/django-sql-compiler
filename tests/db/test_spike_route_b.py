from . import spike_b_cases as cases


def test_route_b_q1_params_default(db_under_test, spike_default):
    cases.check_q1_params('default')


def test_route_b_q2_pinned_alias_default(db_under_test, spike_default):
    cases.check_q2_pinned_alias('default')


def test_route_b_q3_percent_default(db_under_test, spike_default):
    cases.check_q3_percent('default')


def test_route_b_q4_lazy_default(db_under_test, spike_default):
    cases.check_q4_lazy('default')


def test_route_b_q5_no_deprecation_default(db_under_test, spike_default):
    cases.check_q5_no_deprecation('default')


def test_route_b_q6_roundtrip_default(db_under_test, spike_default):
    cases.check_q6_roundtrip('default')


def test_route_b_q6_executable_query_default(db_under_test, spike_default):
    cases.check_q6_executable_query('default')


def test_route_b_q7_clone_default(db_under_test, spike_default):
    cases.check_q7_clone('default')


def test_route_b_q2_mismatch_default_result_on_sqlite_live(db_under_test, spike_default, spike_sqlite):
    cases.check_q2_mismatch('default', 'sqlite_live')


def test_route_b_q2_mismatch_sqlite_live_result_on_default(db_under_test, spike_default, spike_sqlite):
    cases.check_q2_mismatch('sqlite_live', 'default')


def test_route_b_writes_default(db_under_test, spike_default):
    cases.check_b_writes('default')


def test_route_b_writes_hazard_unguarded_update_default(db_under_test, spike_default):
    cases.check_b_writes_hazard_unguarded_update('default')


def test_route_b_rowshape_default(db_under_test, spike_default):
    cases.check_b_rowshape('default')


def test_route_b_joins_default(db_under_test, spike_default):
    cases.check_b_joins('default')


def test_route_b_joins_hazard_real_to_derived_default(db_under_test, spike_default):
    cases.check_b_joins_hazard_real_to_derived('default')


def test_route_b_reads_default(db_under_test, spike_default):
    cases.check_b_reads('default')


def test_route_b_cte_compare_default(db_under_test, spike_default):
    cases.check_b_cte_compare('default')


def test_route_b_mechanisms_default(db_under_test, spike_default):
    cases.check_b_mechanisms('default')


def test_route_b_trim_start_default(db_under_test, spike_default):
    cases.check_b_trim_start('default')
