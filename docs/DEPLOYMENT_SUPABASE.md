# Supabase PostgreSQL for DataSleuth

Create server-side connection strings with the `postgresql+psycopg` driver.
Use a direct connection on port 5432 when the runtime can reach the project's
direct endpoint. For a persistent IPv4-only runtime, copy the session pooler
endpoint and username from the project's **Connect** panel. Hosted validation
requires port 5432 and `sslmode=verify-full`. Use the CA trusted by the selected
endpoint and include the local certificate path in `sslrootcert` when using a
mounted certificate. Percent-encode credentials and query values as needed.
[Supabase connection modes and TLS](https://supabase.com/docs/guides/database/connecting-to-postgres)

Example structure for an IPv4 session pooler connection:

```text
postgresql+psycopg://ROLE.PROJECT_REF:PASSWORD@POOLER_HOST:5432/postgres?sslmode=verify-full&sslrootcert=/etc/secrets/supabase-ca.crt
```

Both runtime services use `DATABASE_URL`. Use a restricted login role with
schema usage and the table privileges needed by the API and worker, including
read access to `alembic_version`. Keep the application in a dedicated schema
outside the Supabase Data API's exposed schemas. Configure the same default
`search_path` for both roles so migrations and runtime queries resolve to
that schema. Grant new table privileges through the migration role or its
default privileges. Keep database credentials off the frontend.

Use a separate schema-owner login and a verified direct PostgreSQL connection
for `MIGRATION_DATABASE_URL` whenever reachable. The IPv4 session pooler is
the persistent fallback. Keep this credential in the authorised one-off
migration environment and set `DATASLEUTH_MODE=hosted` there. Alembic opens
one unpooled connection. Pass the certificate to the migration environment
as well. Verify the target database and back up an existing installation
before applying a migration. The current head is `0008_private_documents`.

One API process uses at most three pooled connections and one worker at most
two, with zero overflow. Reserve capacity for deployment overlap, migration,
Supabase services and administration before scaling. A pool acquisition
times out after three seconds and a new connection after four seconds.
[Supabase pooling and limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits)

Local Docker verification used certificate and hostname verification against a
disposable PostgreSQL server. Supabase routing, certificate deployment and
restricted role grants still require staging verification.
