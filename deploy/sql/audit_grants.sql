-- Make the audit table insert-only for the application's database role (ADMIN_FOUNDATION s.7).
--
-- Run as the postgres SUPERUSER, once, right after the audit migration has created the table:
--
--   sudo -u postgres psql -v app_role=flowly -d flowly -f /var/www/flowly/deploy/sql/audit_grants.sql
--
-- app_role is the role named in DATABASE_URL (backend/.env on the server). Safe to run again.
--
-- Why a separate owner: a table owner can always grant itself UPDATE and DELETE back. So the table is owned by a
-- role that cannot log in (flowly_audit_owner), and the app role only gets SELECT and INSERT.
--
-- Check afterwards, as the app role (psql -U flowly -h localhost -d flowly):
--   INSERT works; SELECT works; UPDATE audit_entries SET reason = 'x';  -> ERROR: permission denied
--                                DELETE FROM audit_entries;             -> ERROR: permission denied
--
-- A later migration that alters audit_entries must run as postgres, or first give the table back:
--   sudo -u postgres psql -d flowly -c 'ALTER TABLE audit_entries OWNER TO flowly;'     (before migrate)
--   ... run the migration as the app role ...
--   sudo -u postgres psql -v app_role=flowly -d flowly -f /var/www/flowly/deploy/sql/audit_grants.sql   (after)
-- Rolling back the audit migration itself (migrate audit zero) needs the same "give it back" step first.
--
-- Undo (back to a normal app-owned table):
--   sudo -u postgres psql -d flowly -c 'ALTER TABLE audit_entries OWNER TO flowly;' \
--                                    -c 'GRANT ALL ON TABLE audit_entries TO flowly;' \
--                                    -c 'GRANT ALL ON SEQUENCE audit_entries_id_seq TO flowly;'
--   sudo -u postgres psql -d flowly -c 'DROP ROLE IF EXISTS flowly_audit_owner;'   (optional)
--
-- This blocks the application only. A database administrator can still change rows, so that use must be logged
-- outside the application (see ADMIN_FOUNDATION s.7).

\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'flowly_audit_owner') THEN
    CREATE ROLE flowly_audit_owner NOLOGIN;
  END IF;
END
$$;

-- Moving the table also moves its id sequence (owned by the id column).
ALTER TABLE audit_entries OWNER TO flowly_audit_owner;

REVOKE ALL ON TABLE audit_entries FROM PUBLIC;
REVOKE ALL ON TABLE audit_entries FROM :"app_role";
GRANT SELECT, INSERT ON TABLE audit_entries TO :"app_role";

-- INSERT needs the id sequence.
REVOKE ALL ON SEQUENCE audit_entries_id_seq FROM PUBLIC;
GRANT USAGE, SELECT ON SEQUENCE audit_entries_id_seq TO :"app_role";

COMMIT;
