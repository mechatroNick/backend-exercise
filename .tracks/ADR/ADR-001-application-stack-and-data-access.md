# ADR-001: Application stack and data-access boundaries

- Status: Accepted
- Date: 2026-08-05
- Decision owners: Repository owner
- Affected tracks: 01-08
- Affected SPEC versions: Baseline
- Supersedes: None
- Superseded by: None

## Context

The assessment requires a locally runnable REST API with relational modelling,
migrations, JWT authentication, OpenAPI documentation, efficient ORM queries, and
one explicitly raw-SQL statistics capability. The implementation must be small
enough to explain in a follow-up walkthrough while still demonstrating production
engineering discipline.

## Decision

- Use Python 3.12, FastAPI, synchronous SQLModel sessions, SQLite, Alembic, and
  Uvicorn.
- Use a modular monolith with feature modules for authentication and bookmarks.
- Use SQLModel table classes only for persistence and separate non-table SQLModel
  DTOs for create, patch, query, public response, pagination, authentication,
  errors, health, and statistics contracts.
- Use request-scoped SQLModel sessions. Sessions are never shared between request
  handlers and background threads.
- Use Alembic revisions as the only application schema-creation mechanism. Do not
  call `SQLModel.metadata.create_all()` during application startup.
- Enable `PRAGMA foreign_keys=ON` for every SQLite connection through an engine
  connection hook, including application, migration, test, and background-service
  connections.
- Express uniqueness, composite keys, foreign keys, deletion behavior, indexes,
  and length checks in generated migration DDL. Do not rely on SQLite accepting a
  declared `VARCHAR(n)` length as enforcement.
- Model `bookmark_tags` as an explicit SQLModel link table whose two foreign keys
  form a composite primary key.
- Use SQLModel ORM for all ordinary persistence and queries. Raw SQL is isolated to
  the statistics subsystem: the assessment-required current aggregate reader and the
  event-time window aggregate reader. Each raw query is explained with a concise
  source comment.
- Run one Uvicorn application worker while the background statistics service is
  in-process. Multi-process scaling requires extracting or coordinating that
  service and is outside the assessed runtime.

## Alternatives considered

| Alternative | Benefits | Costs and risks | Reason not selected |
| --- | --- | --- | --- |
| SQLAlchemy without SQLModel | Maximum ORM flexibility | Separate Pydantic and ORM declarations add repetition | SQLModel was explicitly selected and fits the exercise |
| Async SQLModel/SQLAlchemy | Useful for highly concurrent I/O workloads | More lifecycle, driver, transaction, and test complexity with no measured need | Synchronous access is clearer for local SQLite |
| PostgreSQL as the required runtime | Stronger production concurrency | Adds local service setup and obscures the zero-setup assessment path | SQLite is explicitly recommended by the brief |
| Dual SQLite/PostgreSQL support | Demonstrates portability | Raw date SQL, migrations, and test matrix become dialect-dependent | Unsupported portability claims reduce clarity |

## Consequences

### Positive

- A fresh local setup has no external database dependency.
- API and persistence contracts remain explicit despite SQLModel sharing common
  primitives.
- Database constraints and ownership predicates provide defence in depth.
- The raw-SQL rubric item has a visible, narrow ownership boundary.

### Negative and risks

- The monthly statistics query is intentionally SQLite-specific.
- Synchronous SQLite and a single application worker are not a high-concurrency
  production architecture.
- Alembic autogeneration must be manually inspected because model declarations do
  not prove the emitted DDL is correct.

### Follow-up

- Verify migrations against a brand-new database.
- Test that `PRAGMA foreign_keys` returns `1` and invalid relationships fail.
- Document the production evolution to PostgreSQL and externally coordinated
  background processing without implementing it.

## Evidence and references

- [Assessment](../../docs/Technical%20Assessment%20Senior%20Software_Engineer.pdf)
- [SQLModel multiple API and table models](https://sqlmodel.tiangolo.com/tutorial/fastapi/multiple-models/)
- [SQLModel many-to-many link models](https://sqlmodel.tiangolo.com/tutorial/many-to-many/create-models-with-link/)
- [SQLite foreign-key enforcement](https://www.sqlite.org/foreignkeys.html)
- [Alembic autogeneration](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
