# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-25

The first release since 0.1.1 (June 2021). It ships correctness fixes and first-time MySQL support.

### Added

- MySQL support for `django.db.backends.mysql` (via mysqlclient), contributed in [PR 2](https://github.com/JaredStufftGD/django-sql-compiler/pull/2). It is covered by the live-database test suite and CI. In 0.1.1 the MySQL compiler was a stub and was not registered.

### Fixed

- Non-ASCII parameters are decoded with the connection's encoding instead of byte by byte, so values like `café` are no longer garbled. 0.1.1 corrupted them.
- SQL is compiled for the queryset's own database alias (`.using()` or a database router) instead of the default alias.
- The unsupported-backend error names the ENGINE instead of saying "None backend is not supported".

### Changed

- Decoding is strict. Compiler output that can't be decoded with the connection's codec raises `UnicodeDecodeError` (or `LookupError` for an unknown client encoding) instead of returning garbled text. A Postgres connection on `SQL_ASCII`, or another unusual client encoding, with non-ASCII data now raises where 0.1.1 returned text. A compiler that returns non-bytes raises `TypeError`.
- Semi-public API:
  - `sql_compiler.utils.bytes_to_string` now requires an `encoding` argument.
  - `BaseSQLCompiler` has a new `python_encoding(connection)` method that custom compiler subclasses must implement (the base raises `NotImplementedError`).
  - `MySQLCompiler` is exported from `sql_compiler.compilers`.
- Install requirements: Python >=3.10 and Django >=4.2. The package declares no database driver (psycopg2 or mysqlclient comes from your Django setup). Effects on existing environments:
  - With an older Django installed but not pinned, upgrading django-sql-compiler can upgrade Django (accepted, because Django <4.2 is end-of-life).
  - With Django <4.2 pinned, or on Python <3.10, pip stays on 0.1.1.
  - An install from git master already reports 0.2.3, so pip won't treat 0.2.0 as an upgrade. Install `django-sql-compiler==0.2.0` explicitly.

### Packaging

- Ships a wheel again (0.1.1 was sdist-only; 0.0.5a0 and 0.1.0 had wheels).
- Built with flit_core instead of setuptools.
- The license is declared with PEP 639 `License-Expression: MIT`, and LICENSE ships in both artifacts.
- Metadata-Version 2.5.
- CHANGELOG.md ships in the sdist.

### Known issues

- psycopg 3 is not supported yet. With psycopg 3 installed, Django uses it and `executable_query` raises (planned for 1.0). 0.1.1 had this issue too.
- `.none()` querysets raise `EmptyResultSet` (planned for 1.0). 0.1.1 had this issue too.

[0.2.0]: https://github.com/JaredStufftGD/django-sql-compiler/releases/tag/v0.2.0
