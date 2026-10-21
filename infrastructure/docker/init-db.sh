#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv migration_password ASHANA_MIGRATION_PASSWORD
\getenv app_password ASHANA_APP_PASSWORD
SELECT format('CREATE ROLE ashana_migrator LOGIN PASSWORD %L', :'migration_password') \gexec
SELECT format('CREATE ROLE ashana_app LOGIN PASSWORD %L', :'app_password') \gexec
ALTER DATABASE ashana OWNER TO ashana_migrator;
REVOKE ALL ON DATABASE ashana FROM PUBLIC;
GRANT CONNECT ON DATABASE ashana TO ashana_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO ashana_migrator;
GRANT USAGE ON SCHEMA public TO ashana_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ashana_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ashana_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ashana_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ashana_app;
SQL
