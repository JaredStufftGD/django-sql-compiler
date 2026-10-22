<!-- refreshed: 2026-10-22 -->
# Architecture

**Analysis Date:** 2026-10-22

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                  Consumer Django project                     │
│   Model.objects (SQLCompilerManager)  →  .executable_query   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Public API / QuerySet layer                  │
│  `sql_compiler/manager.py`  `sql_compiler/queryset.py`       │
└───────┬──────────────────────────────┬──────────────────────┘
        │ validate                     │ compile
        ▼                              ▼
┌──────────────────────┐   ┌─────────────────────────────────────┐
│ Connection validation │   │ Compiler registry & backend classes  │
│ `sql_compiler/utils.py`│  │ `sql_compiler/compilers/__init__.py` │
│                      │   │ `compilers/base.py`                 │
└──────────────────────┘   │ `compilers/postgresql.py`           │
                            │ `compilers/mysql.py`                │
                            └──────────────────┬──────────────────┘
                                               │ uses DB cursor
                                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Django `connections[alias]` → driver (psycopg2 / MySQLdb)   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Package facade | Re-exports `SQLCompilerManager` and `SQLCompilerQuerySet` | `sql_compiler/__init__.py` |
| Manager | Subclasses Django `Manager`; `get_queryset()` returns the custom queryset | `sql_compiler/manager.py` |
| QuerySet | Owns `executable_query` (cached property): validate, build SQL+params, compile, decode | `sql_compiler/queryset.py` |
| Connection validation | Checks the connection ENGINE against the supported list; decodes driver bytes to `str` | `sql_compiler/utils.py` |
| Compiler registry | Builds `compilers`, `compiler_map` (ENGINE → class) and `SUPPORTED_BACKENDS` from one list | `sql_compiler/compilers/__init__.py` |
| Base compiler | Defines `backend_name` slot and abstract `compile_sql` | `sql_compiler/compilers/base.py` |
| Postgres compilers | Delegate to psycopg2 `cursor.mogrify`; subclasses only change `backend_name` | `sql_compiler/compilers/postgresql.py` |
| MySQL compiler | Reimplements mogrify with `connection.literal()` and `%` formatting | `sql_compiler/compilers/mysql.py` |
| Packaging | Distribution metadata, version (0.2.3), `find_packages()` | `setup.py` |

## Pattern Overview

**Overall:** Thin library layer: a Django manager/queryset extension that delegates SQL rendering to a per-backend strategy class registered in a dictionary keyed by Django's `ENGINE` string.

**Key Characteristics:**
- No models, migrations, views, or URLs. `sql_compiler` is a Django-installable app in name only (no `models.py`), used for its manager/queryset.
- Strategy pattern for backends: `BaseSQLCompiler` subclasses are looked up by `connection.settings_dict['ENGINE']`.
- Registry is derived, not hand-maintained twice: `compiler_map` and `SUPPORTED_BACKENDS` are computed from the `compilers` list in `sql_compiler/compilers/__init__.py`.
- Compilers are stateless and instantiated per call (`compiler_map[backend_name]()` in `sql_compiler/queryset.py`).
- The library does not import any DB driver directly. Drivers are reached only through the Django connection's cursor (`connection.cursor()`), so psycopg2 / MySQLdb are the consumer's responsibility.
- Requires a live database connection: compilation executes through a real cursor, so `executable_query` cannot be produced offline.

## Layers

**Public API layer (manager + queryset):**
- Purpose: Expose `executable_query` on any `QuerySet` from a model whose manager is `SQLCompilerManager`.
- Location: `sql_compiler/manager.py`, `sql_compiler/queryset.py`
- Contains: `SQLCompilerManager(Manager)`, `SQLCompilerQuerySet(QuerySet)`, `executable_query` cached property.
- Depends on: `django.db.connections`, `django.db.models`, `sql_compiler.utils`, `sql_compiler.compilers`.
- Used by: Consumer code (`MyModel.objects.filter(...).executable_query`).

**Utility layer:**
- Purpose: Connection gating and byte-to-string decoding.
- Location: `sql_compiler/utils.py`
- Contains: `validate_connection(connection)`, `bytes_to_string(bytes_obj)`.
- Depends on: `sql_compiler.compilers.SUPPORTED_BACKENDS`.
- Used by: `sql_compiler/queryset.py`.

**Compiler layer (strategy classes):**
- Purpose: Turn `(query_sql, params)` into fully interpolated, escaped SQL as bytes.
- Location: `sql_compiler/compilers/`
- Contains: `base.py` (`BaseSQLCompiler`), `postgresql.py` (`PostgresCompiler`, `PostgresTenantsCompiler`, `Psycopg2Compiler`), `mysql.py` (`MySQLCompiler`), registry in `__init__.py`.
- Depends on: Django connection cursor and, for MySQL, `connection.literal` / `cursor.connection.encoding` from the driver.
- Used by: `SQLCompilerQuerySet.executable_query` only.

**Packaging layer:**
- Purpose: Ship the package to PyPI.
- Location: `setup.py`, `README.md` (also used as `long_description`).
- Contains: Metadata, `install_requires=['django']` only.

## Data Flow

### Primary Request Path

1. Consumer accesses `.executable_query` on a `SQLCompilerQuerySet` (`sql_compiler/queryset.py`, `executable_query`). The result is memoized on that queryset instance by `cached_property`; chaining `.filter()` returns a new queryset, so no stale value is carried over.
2. `utils.validate_connection(connections[self.db])` reads `settings_dict['ENGINE']` and returns the connection if it is in `SUPPORTED_BACKENDS`, otherwise `None` (`sql_compiler/utils.py`).
3. `self.query.sql_with_params()` produces parameterized SQL and a params tuple from Django's internal `Query` object (`sql_compiler/queryset.py`).
4. `compilers.compiler_map[backend_name]()` selects and instantiates the compiler class (`sql_compiler/compilers/__init__.py`).
5. `compiler.compile_sql(connection, query, params)` opens `connection.cursor()` and returns bytes:
   - Postgres: `cursor.mogrify(query, params)` (`sql_compiler/compilers/postgresql.py`).
   - MySQL: `MySQLCompiler.mogrify` substitutes `db.literal(item)` values into the `%s` / `%(name)s` placeholders (`sql_compiler/compilers/mysql.py`).
6. `utils.bytes_to_string` converts the bytes to `str` via `chr()` per byte (`sql_compiler/utils.py`). The result is returned to the consumer.

### Secondary Flow: Unsupported backend

1. `validate_connection` returns `None` for an unknown ENGINE.
2. `executable_query` raises `NotImplementedError` (`sql_compiler/queryset.py`). See Anti-Patterns below for the message problem.

**State Management:**
- No persistent state. The only state is the `cached_property` result on each queryset instance and the module-level `compiler_map` / `SUPPORTED_BACKENDS` constants, which are built once at import time.

## Key Abstractions

**`BaseSQLCompiler`:**
- Purpose: Contract for backend-specific SQL rendering.
- Examples: `sql_compiler/compilers/base.py`
- Pattern: Class attribute `backend_name` (the Django ENGINE string) plus instance method `compile_sql(connection, query, params) -> bytes`. Base raises `NotImplementedError`.

**Compiler registry:**
- Purpose: Single list of supported backends that drives both dispatch and validation.
- Examples: `sql_compiler/compilers/__init__.py` (`compilers`, `compiler_map`, `SUPPORTED_BACKENDS`)
- Pattern: Dict comprehension keyed by `backend_name`. Duplicate `backend_name` values would silently overwrite each other.

**Postgres compiler family:**
- Purpose: Same mogrify logic under several Django ENGINE strings.
- Examples: `PostgresCompiler` (`django.db.backends.postgresql`), `Psycopg2Compiler` (`django.db.backends.postgresql_psycopg2`), `PostgresTenantsCompiler` (`django_tenants.postgresql_backend`) in `sql_compiler/compilers/postgresql.py`.
- Pattern: Subclass overrides only `backend_name`; no behavior change.

## Entry Points

**Model manager:**
- Location: `sql_compiler/manager.py` (`SQLCompilerManager`)
- Triggers: Consumer declares `objects = SQLCompilerManager()` on a model (per `README.md`).
- Responsibilities: Returns `SQLCompilerQuerySet` from `get_queryset()`, so all manager-level queries carry the executable property.

**QuerySet property:**
- Location: `sql_compiler/queryset.py` (`SQLCompilerQuerySet.executable_query`)
- Triggers: Attribute access on any queryset produced by the manager.
- Responsibilities: Full compile pipeline described in Primary Request Path.

**Package import:**
- Location: `sql_compiler/__init__.py`
- Triggers: `from sql_compiler import SQLCompilerManager` (per `README.md`).
- Responsibilities: Re-exports the manager and queryset. Importing it also imports `sql_compiler.compilers`, which builds the registry.

## Architectural Constraints

- **Threading:** No threading or async code. Each `executable_query` call uses `connections[alias]`, which Django keeps thread-local, so concurrent use follows Django's per-thread connection model.
- **Global state:** Module-level registry in `sql_compiler/compilers/__init__.py` (`compilers`, `compiler_map`, `SUPPORTED_BACKENDS`). `SUPPORTED_BACKENDS` is a live `dict_keys` view of `compiler_map`. No mutable state is written after import.
- **Database routing:** `executable_query` validates and executes against `connections[self.db]`, but `self.query.sql_with_params()` is called without a database argument. In Django's `Query` implementation this compiles SQL through the default alias's connection operations (not verified in this repo; Django is not installed in the workspace). Multi-database routing with non-default backends may therefore produce SQL that does not match the executing connection.
- **Driver coupling:** `compilers/mysql.py` and `compilers/postgresql.py` do not import `MySQLdb` or `psycopg2`. They rely on the methods exposed by the live cursor/connection (`mogrify`, `literal`, `encoding`).
- **Return type contract:** `compile_sql` must return `bytes` (or an object iterable of ints), because `utils.bytes_to_string` iterates over the result. A `str` return breaks decoding (see Anti-Patterns).
- **Circular imports:** None. Import order is `queryset` → `utils` → `compilers`; `manager` → `queryset`. `compilers/__init__.py` does not import from the package root.
- **Test suite:** None in the repository. Behavior is verified only against a live Django project (per `CLAUDE.md`).

## Anti-Patterns

### Byte-wise decoding in `bytes_to_string`

**What happens:** `sql_compiler/utils.py` builds the string with `"".join([chr(c) for c in bytes_obj])`, which treats each byte as a Latin-1 code point.
**Why it's wrong:** Driver output from psycopg2 and MySQLdb is UTF-8 for non-ASCII data. A multi-byte UTF-8 character becomes several unrelated characters (mojibake). The result is also not what the database would accept as a literal.
**Do this instead:** Decode with the connection encoding, for example `bytes_obj.decode(connection.connection.encoding or 'utf-8')` or `bytes_obj.decode('utf-8')`, in `sql_compiler/utils.py` and call it from `sql_compiler/queryset.py`.

### Unimported exception in `MySQLCompiler.mogrify`

**What happens:** `sql_compiler/compilers/mysql.py` raises `ProgrammingError(str(m))` on a `TypeError` during `query % args`, but `ProgrammingError` is not imported in that module.
**Why it's wrong:** The intended error becomes a `NameError`, hiding the real formatting problem.
**Do this instead:** Import the driver's exception (`from MySQLdb import ProgrammingError`) or use `django.db.utils.ProgrammingError`, following `sql_compiler/compilers/mysql.py`.

### Misleading unsupported-backend error

**What happens:** In `sql_compiler/queryset.py`, `if not connection:` runs after `utils.validate_connection` returns `None`, and the message is built with `str(connection)`.
**Why it's wrong:** `connection` is `None` at that point, so the message reads `"None backend is not supported."` and omits the ENGINE that was rejected.
**Do this instead:** Build the message from `self.db` / `connections[self.db].settings_dict['ENGINE']` before validation, in `sql_compiler/queryset.py`.

### Hand-maintained backend list in documentation

**What happens:** `README.md` ("Backend Support") lists only `django.db.backends.postgresql` and `django.db.backends.mysql`.
**Why it's wrong:** `sql_compiler/compilers/__init__.py` also registers `django.db.backends.postgresql_psycopg2` and `django_tenants.postgresql_backend`. Docs drift from the registry.
**Do this instead:** Update the list in `README.md` whenever `compilers` in `sql_compiler/compilers/__init__.py` changes, as `CLAUDE.md` requires.

## Error Handling

**Strategy:** Fail fast on unsupported backends; otherwise let driver and Django exceptions propagate.

**Patterns:**
- Unsupported ENGINE: `validate_connection` returns `None`, then `NotImplementedError` in `sql_compiler/queryset.py`.
- Base compiler: `BaseSQLCompiler.compile_sql` raises `NotImplementedError` in `sql_compiler/compilers/base.py`.
- Database errors from `cursor.mogrify` or `literal` propagate unchanged to the caller.

## Cross-Cutting Concerns

**Logging:** None. No logging calls in the package.
**Validation:** Only backend ENGINE validation (`sql_compiler/utils.py`). Query and parameter validation is delegated to Django and the driver.
**Authentication:** Not applicable. Uses the consumer's configured Django database connections.

---

*Architecture analysis: 2026-10-22*
