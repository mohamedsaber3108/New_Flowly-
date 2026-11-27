-- Make the audit table insert-only for the application's database role (ADMIN_FOUNDATION s.7).
--
-- Run ONCE after the audit migration, as the database owner or a superuser (NOT as the app role):
--
--   sudo -u postgres psql -d flowly -v app_role=flowly -f /var/www/flowly/deploy/sql/audit_grants.sql
--
-- app_role is the role named in DATABASE_URL (see backend/.env on the server). Safe to run again.
-- Check afterwards, as the app role: an UPDATE or DELETE on audit_entries must say "permission denied".
-- To undo: GRANT UPDATE, DELETE ON audit_entries TO :"app_role";
--
-- Note: this blocks the application only. A database administrator can still change rows, so that use
-- must be logged outside the application (see ADMIN_FOUNDATION s.7).

\set ON_ERROR_STOP on

REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_entries FROM :"app_role";
GRANT SELECT, INSERT ON TABLE audit_entries TO :"app_role";
-- The id sequence is needed for INSERT.
GRANT USAGE, SELECT ON SEQUENCE audit_entries_id_seq TO :"app_role";
