# Codebase Concerns

**Analysis Date:** 2026-10-22

## Tech Debt

**Hand-rolled MySQL parameter interpolation:**
- Issue: `MySQLCompiler` reimplements what `cursor.mogrify` does for psycopg2 by calling `db.literal()` on each param and then doing a `%` substitution on the raw query bytes. This duplicates driver logic and bypasses MySQLdb's own parameter handling.
- Files: `sql_compiler/compilers/mysql.py` (`mogrify`, lines 13-33)
- Impact: Any divergence from how MySQLdb's `execute()` quotes or formats values (dict vs. tuple params, `%%` escaping, `None`, `datetime`, `Decimal`, bytes) produces SQL that differs from what Django would actually send. The behavior is untested (see Test Coverage Gaps).
- Fix approach: Verify parity against `MySQLdb.cursors.BaseCursor._query`/`cursor.mogrify` on the pinned mysqlclient version, and add tests comparing output for each param type. Or delegate to a supported driver API if one exists.

**Duplicated compiler classes for Postgres:**
- Issue: `PostgresCompiler`, `PostgresTenantsCompiler`, and `Psycopg2Compiler` in `sql_compiler/compilers/postgresql.py` are identical except for `backend_name`. Each new engine alias requires a new class plus an entry in the list in `sql_compiler/compilers/__init__.py`.
- Files: `sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/__init__.py`
- Impact: Low on its own, but it is the pattern that makes adding aliases easy to get wrong (e.g. a class missing from the `compilers` list silently makes that ENGINE unsupported, because `SUPPORTED_BACKENDS` is derived from that list).
- Fix approach: Accept a tuple of backend names on one class, or keep the subclasses and add a test asserting every ENGINE the package claims to support appears in `compiler_map`.

**Hard-coded `ProgrammingError` without import:**
- Issue: `MySQLCompiler.mogrify` raises `ProgrammingError(str(m))` on a `TypeError`, but `ProgrammingError` is never imported in `sql_compiler/compilers/mysql.py`.
- Files: `sql_compiler/compilers/mysql.py` (line 31)
- Impact: The intended error path raises `NameError` instead, hiding the real parameter-count/type mismatch from the user. See Known Bugs.
- Fix approach: Import the exception from the driver (`MySQLdb.ProgrammingError`) or from `django.db` and re-raise with the original message.

**Misleading "unsupported backend" message:**
- Issue: In `SQLCompilerQuerySet.executable_query`, the check `if not connection:` runs after `validate_connection` returns `None` for unsupported engines. The message is built with `str(connection)`, which is always `'None'` at that point.
- Files: `sql_compiler/queryset.py` (lines 18-21), `sql_compiler/utils.py` (lines 13-15)
- Impact: Users on an unsupported database see `None backend is not supported.` and cannot tell which ENGINE is configured.
- Fix approach: Read `connections[self.db].settings_dict['ENGINE']` before validation and include it in the message, e.g. `'{} backend is not supported.'.format(engine)`.

**Documentation drift on supported backends:**
- Issue: `README.md` ("Backend Support") says only `django.db.backends.postgresql` and `django.db.backends.mysql` are supported. The code also accepts `django.db.backends.postgresql_psycopg2` and `django_tenants.postgresql_backend`. `CLAUDE.md` requires the README section to be updated whenever a backend is added.
- Files: `README.md`, `sql_compiler/compilers/postgresql.py`, `sql_compiler/compilers/__init__.py`
- Impact: Users of `django_tenants` may assume it is unsupported, or rely on undocumented behavior.
- Fix approach: List all four ENGINE strings in README, and note `postgresql_psycopg2` is a legacy alias.

**Version and packaging metadata:**
- Issue: `setup.py` declares `install_requires=['django']` with no version floor, and no driver extra (psycopg2 or mysqlclient) is declared. `setup.py` reads `README.md` with a bare `open()` (no encoding, no context manager). The version `0.2.3` is hard-coded in `setup.py`.
- Files: `setup.py`
- Impact: Installs against untested Django versions. On Windows, the default codepage is used to read the README during build. Users have to install the driver themselves, and nothing warns them if it is missing.
- Fix approach: Pin a tested Django range, use `with open('README.md', encoding='utf-8')`, and add optional extras such as `postgres = ['psycopg2-binary']` and `mysql = ['mysqlclient']`.

## Known Bugs

**Non-ASCII parameters are corrupted in `executable_query` output:**
- Symptoms: Any non-ASCII character in a filter value (e.g. `name='José'`, `'東京'`) comes out as mojibake in the compiled SQL, such as `'JosÃ©'`. Executing that SQL stores or matches the wrong data without raising an error.
- Files: `sql_compiler/utils.py` (`bytes_to_string`, line 24), used from `sql_compiler/queryset.py` (line 28)
- Trigger: Any queryset with a non-ASCII string parameter on either backend. The driver returns UTF-8 (or the connection charset) bytes, and `bytes_to_string` maps each byte to a Latin-1 character with `chr(c)`, so multi-byte characters are split.
- Workaround: None inside the package. Users can avoid non-ASCII filter values, or re-encode the result themselves (`result.encode('latin-1').decode('utf-8')`), which is fragile.
- Fix approach: Decode using the connection's encoding, e.g. `bytes.decode(connection.connection.encoding)` for psycopg2 and `db.encoding` for MySQLdb, and add a test with a multi-byte string. Replacing the per-byte list comprehension also removes a Python-level loop over the entire SQL text.

**`executable_query` compiles with the default database, not the routed one:**
- Symptoms: On a multi-database project, the SQL text is generated by the default alias's compiler while execution uses `connections[self.db]`. If the two aliases use different vendors (e.g. default is PostgreSQL and the routed alias is MySQL), the SQL is quoted for the wrong backend and fails when run.
- Files: `sql_compiler/queryset.py` (line 23, `self.query.sql_with_params()`)
- Trigger: A router sends queries for a model to a non-default alias with a different engine. The Django implementation of `Query.sql_with_params()` compiles against `DEFAULT_DB_ALIAS`; verify this against the Django version in use.
- Workaround: Use a single-database project, or set `DEFAULT_DB_ALIAS` to the same engine.
- Fix approach: Compile with the queryset's alias, e.g. `self.query.get_compiler(using=self.db).as_sql()`, and keep the same `using=` value everywhere in the path.

**Empty querysets are not handled:**
- Symptoms: `.none()` querysets raise an exception from the Django compiler (Django's internal `EmptyResultSet`) rather than returning an empty SQL result, because `sql_with_params()` is called with no handling for it. This is expected to occur but has not been verified against a live database.
- Files: `sql_compiler/queryset.py` (line 23)
- Trigger: `Model.objects.none().executable_query`
- Workaround: Avoid `.none()` before calling `executable_query`, or catch the exception and substitute a `SELECT ... WHERE FALSE` query.
- Fix approach: Catch the empty-result case and produce a valid empty query for the target backend.

## Security Considerations

**Output is not safe to splice into SQL that is run with parameters:**
- Risk: `executable_query` returns SQL with every value inlined as a literal. The README shows embedding it in `Model.objects.raw(wrapper_query)`. If a caller then passes params to `raw()` or `cursor.execute(sql, params)`, the driver treats any `%` inside the inlined literals (e.g. `LIKE '%50%'`) as a placeholder and fails or substitutes incorrectly.
- Files: `sql_compiler/queryset.py`, `README.md` (Usage section)
- Current mitigation: Values are escaped by the driver, so injection through the parameter values themselves is prevented when the output is used as-is.
- Recommendations: Document that the output must not be passed with a params argument, or escape `%` to `%%` in the returned string. Add a test that the output of a `LIKE` filter can be executed alongside params.

**Full literal values are embedded in the returned string:**
- Risk: The returned SQL contains every filter value in plaintext. If it is logged, displayed in an admin UI, or cached, sensitive values (emails, tokens, personal data) leak.
- Files: `sql_compiler/queryset.py`
- Current mitigation: None. The package does not log or store the output itself.
- Recommendations: Note this in the README. Callers should treat `executable_query` output as sensitive.

**Developer-supplied SQL is concatenated without validation:**
- Risk: The README pattern `"""select ... from ({}) a""".format(executable_query)` is safe for the compiled query, but any surrounding SQL that uses user input directly (not through the ORM) reintroduces injection. The package offers no guard for this.
- Files: `README.md` (Usage section)
- Current mitigation: Documentation only.
- Recommendations: Keep the README examples on parameterized `raw(sql, params)` for user input and reserve `executable_query` for ORM-generated fragments.

## Performance Bottlenecks

**Per-byte Python loop in `bytes_to_string`:**
- Problem: Every character of the compiled SQL is converted with a Python-level `chr()` call in a list comprehension, then joined.
- Files: `sql_compiler/utils.py` (line 24)
- Cause: Byte-by-byte conversion instead of a codec decode.
- Improvement path: Replace with `bytes_obj.decode(encoding)`, which is also the fix for the Known Bugs entry above. For large generated queries (multi-megabyte `IN` lists), this is measurably slower than a native decode.

**Full SQL compile on every `executable_query` access per queryset instance:**
- Problem: Each `SQLCompilerQuerySet` instance compiles and caches its own SQL. Building the same query in several places recompiles it each time, and each compile opens a cursor on the connection.
- Files: `sql_compiler/queryset.py` (`cached_property` at line 10)
- Cause: The cache is per-instance, and `cached_property` is not invalidated if the underlying `query` is mutated after first access (e.g. via `qs.query.add_q(...)`).
- Improvement path: Document that the property is computed once per instance and must not be read before the queryset is finished building, or compute it on demand without caching.

## Fragile Areas

**Compiler registration by string key:**
- Files: `sql_compiler/compilers/__init__.py`, `sql_compiler/utils.py`, `sql_compiler/queryset.py`
- Why fragile: The ENGINE string is the only link between Django settings and the compiler. `validate_connection` checks `SUPPORTED_BACKENDS` and `queryset.py` then indexes `compiler_map` with the same string. Any change to one of these lists without the other causes a `KeyError` or silent unsupported-engine failure. `SUPPORTED_BACKENDS` is a live `dict_keys` view of `compiler_map`, so it is not a snapshot.
- Safe modification: Add new backends only through the `compilers` list in `sql_compiler/compilers/__init__.py`, as `CLAUDE.md` describes. Do not hard-code ENGINE strings elsewhere.
- Test coverage: None. No test asserts that the set of ENGINE strings in `compiler_map` matches the README.

**Driver API dependency on psycopg2:**
- Files: `sql_compiler/compilers/postgresql.py` (line 14, `cursor.mogrify`)
- Why fragile: `cursor.mogrify` is a psycopg2 method. Django 4.2+ can also use psycopg 3 under the same `django.db.backends.postgresql` ENGINE. Whether a psycopg 3 cursor exposes `mogrify` with the same semantics has not been verified, so the package may fail or behave differently for those installs.
- Safe modification: Check `connection.vendor`/driver module before calling `mogrify`, and raise a clear error for unsupported drivers.
- Test coverage: None.

**Reliance on Django internals:**
- Files: `sql_compiler/queryset.py` (`self.query.sql_with_params()`), `sql_compiler/manager.py` (`get_queryset`, `self._db`)
- Why fragile: `Query.sql_with_params()` is undocumented, and `Manager._db` is a private attribute. Either may change between Django releases.
- Safe modification: Pin tested Django versions and run the verification steps below after upgrading Django.
- Test coverage: None.

## Scaling Limits

**Compiled SQL size:**
- Current capacity: Not measured. The conversion loop is linear in SQL length, and the full SQL text is held in memory as a `str` alongside the `bytes` from the driver.
- Limit: Very large `IN (...)` lists or deeply nested querysets roughly double peak memory during conversion.
- Scaling path: Decode with a native codec (see Performance Bottlenecks) and avoid keeping both representations.

## Dependencies at Risk

**`django` (unpinned):**
- Risk: No minimum or maximum Django version is declared in `setup.py`. The code depends on `django.utils.functional.cached_property`, `Manager._db`, and `Query.sql_with_params()`.
- Impact: A future Django release that changes or removes any of these breaks `executable_query` without a clear error.
- Migration plan: Declare and test a supported Django range, and add a CI job against the newest release.

**`mysqlclient` and `psycopg2` (not declared):**
- Risk: The package calls into `MySQLdb` and `psycopg2` APIs without declaring either as a dependency.
- Impact: Installing the package in a project that uses another driver yields `AttributeError` at query time, not at install time.
- Migration plan: Declare them as optional extras and check the driver in `validate_connection`.

## Missing Critical Features

**No automated tests or CI:**
- Problem: The repository has no test suite, linter configuration, or CI workflow. `CLAUDE.md` confirms that verification requires a live database.
- Blocks: Safe refactoring of the compilers, confident releases, and regression testing for the Known Bugs above.

**No handling of unsupported Django features in `executable_query`:**
- Problem: Querysets using `union()`, `distinct(fields)`, `select_for_update()`, or database functions that compile differently per vendor are not checked. Their output is not verified against the target database.
- Blocks: Reliable use of `executable_query` for analytics queries that rely on those features.

## Test Coverage Gaps

**All compilers and utilities:**
- What's not tested: Everything. No test files exist in the repository.
- Files: `sql_compiler/compilers/base.py`, `sql_compiler/compilers/mysql.py`, `sql_compiler/compilers/postgresql.py`, `sql_compiler/queryset.py`, `sql_compiler/utils.py`, `sql_compiler/manager.py`
- Risk: The non-ASCII corruption, the `NameError` in the MySQL error path, the default-alias compile, and the unsupported-engine message are all undetected regressions.
- Priority: High

**Multi-byte and special-character parameters:**
- What's not tested: Non-ASCII strings, `%` inside values, `None`, dates, `Decimal`, and empty `IN` lists on both backends.
- Files: `sql_compiler/utils.py`, `sql_compiler/compilers/mysql.py`, `sql_compiler/compilers/postgresql.py`
- Risk: Silent data corruption in the generated SQL, as in the Known Bugs section.
- Priority: High

**Multi-database routing:**
- What's not tested: A queryset routed to a non-default alias, and a mixed-vendor configuration.
- Files: `sql_compiler/queryset.py`
- Risk: SQL compiled for the wrong backend.
- Priority: Medium

---

*Concerns audit: 2026-10-22*
