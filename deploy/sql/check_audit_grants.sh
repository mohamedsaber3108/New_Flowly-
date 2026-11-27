#!/usr/bin/env bash
# =============================================================================
# Prove deploy/sql/audit_grants.sql works. Used by CI (backend job); also runnable by hand on a scratch database.
#
# Needs a database that already has the audit table (run `manage.py migrate` first) and a SUPERUSER connection
# given through the normal libpq variables: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
# It creates a LOGIN role (default flowly_ci_app) that stands for the application's database role, gives it the
# normal table rights, runs the grants file TWICE (idempotent), then checks as that role:
#   INSERT and SELECT work; UPDATE, DELETE, TRUNCATE, ALTER TABLE, DROP TABLE and GRANT all fail.
# Any wrong result exits non-zero.
#
# Never run this against production: it creates a role with a throwaway password.
# =============================================================================
set -euo pipefail

APP_ROLE="${APP_ROLE:-flowly_ci_app}"
APP_PASSWORD="${APP_PASSWORD:-flowly-ci-only-app}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUPER_USER="${PGUSER:?Set PGUSER (a superuser) and the other PG* variables}"
SUPER_PASSWORD="${PGPASSWORD:-}"

as_super() { PGUSER="$SUPER_USER" PGPASSWORD="$SUPER_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 "$@"; }
as_app() { PGUSER="$APP_ROLE" PGPASSWORD="$APP_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 "$@"; }

fail() { echo "CHECK FAILED: $*" >&2; exit 1; }

# The audit table must exist.
[ "$(as_super -At -c "SELECT to_regclass('public.audit_entries') IS NOT NULL")" = "t" ] || fail "audit_entries does not exist: run migrate first"

echo "==> create the test app role with normal table rights"
as_super -v app_role="$APP_ROLE" -v app_password="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_role', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec
SELECT format('ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE', :'app_role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_role')
\gexec
SELECT format('GRANT ALL ON ALL TABLES IN SCHEMA public TO %I', :'app_role')
\gexec
SELECT format('GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_role')
\gexec
SQL

echo "==> run audit_grants.sql (1st time)"
as_super -v app_role="$APP_ROLE" -f "$HERE/audit_grants.sql"
echo "==> run audit_grants.sql (2nd time: must be idempotent)"
as_super -v app_role="$APP_ROLE" -f "$HERE/audit_grants.sql"

[ "$(as_super -At -c "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'audit_entries'::regclass")" = "flowly_audit_owner" ] \
  || fail "audit_entries is not owned by flowly_audit_owner"

echo "==> as ${APP_ROLE}: INSERT and SELECT must work"
as_app -c "INSERT INTO audit_entries (time, actor_label, actor_role, action, target_type, target_id, reason, result, user_agent, request_id)
           VALUES (now(), 'ci', 'owner', 'settings.change', 'setting', 'ci-check', '', 'success', '', '')"
[ "$(as_app -At -c "SELECT count(*) FROM audit_entries WHERE target_id = 'ci-check'")" -ge 1 ] || fail "SELECT did not see the inserted row"

expect_denied() {
  local label="$1" sql="$2" out
  if out="$(as_app -c "$sql" 2>&1)"; then
    fail "${label} succeeded but must be refused. SQL: ${sql}"
  fi
  case "$out" in
    *"permission denied"*|*"must be owner"*) echo "ok: ${label} refused" ;;
    *) fail "${label} failed for another reason: ${out}" ;;
  esac
}

echo "==> as ${APP_ROLE}: these must all be refused"
expect_denied "UPDATE" "UPDATE audit_entries SET reason = 'x'"
expect_denied "DELETE" "DELETE FROM audit_entries"
expect_denied "TRUNCATE" "TRUNCATE audit_entries"
expect_denied "ALTER TABLE" "ALTER TABLE audit_entries ADD COLUMN ci_extra integer"
expect_denied "DROP TABLE" "DROP TABLE audit_entries"
expect_denied "OWNER change" "ALTER TABLE audit_entries OWNER TO ${APP_ROLE}"

# GRANT by a role without grant option is not an error in PostgreSQL: it prints "no privileges were granted" and
# changes nothing. So run it, then check that the role still has no UPDATE, DELETE or TRUNCATE.
as_app -c "GRANT UPDATE, DELETE, TRUNCATE ON audit_entries TO ${APP_ROLE}" >/dev/null 2>&1 || true
[ "$(as_super -At -c "SELECT has_table_privilege('${APP_ROLE}', 'audit_entries', 'UPDATE')
                             OR has_table_privilege('${APP_ROLE}', 'audit_entries', 'DELETE')
                             OR has_table_privilege('${APP_ROLE}', 'audit_entries', 'TRUNCATE')")" = "f" ] \
  || fail "GRANT by the app role gave it UPDATE, DELETE or TRUNCATE"
echo "ok: GRANT by the app role changed nothing"

[ "$(as_super -At -c "SELECT count(*) FROM audit_entries WHERE target_id = 'ci-check'")" -ge 1 ] || fail "the inserted row is gone"
echo "All audit grant checks passed."
