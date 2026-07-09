-- Supabase access guard for the Stage 1.5 web app.
-- Apply after 001_stage15_core.sql in Supabase. The Python scanner should use
-- the direct Postgres connection string; browser/server reads use Supabase Auth.

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_postings ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_skips ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunity_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_allowed_users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS owner_read_companies ON companies;
DROP POLICY IF EXISTS owner_read_job_sources ON job_sources;
DROP POLICY IF EXISTS owner_read_source_runs ON source_runs;
DROP POLICY IF EXISTS owner_read_job_postings ON job_postings;
DROP POLICY IF EXISTS owner_read_role_evaluations ON role_evaluations;
DROP POLICY IF EXISTS owner_read_evaluation_skips ON evaluation_skips;
DROP POLICY IF EXISTS owner_read_opportunity_reviews ON opportunity_reviews;
DROP POLICY IF EXISTS owner_read_notifications ON notifications;
DROP POLICY IF EXISTS owner_read_allowed_users ON app_allowed_users;

CREATE POLICY owner_read_companies ON companies
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_job_sources ON job_sources
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_source_runs ON source_runs
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_job_postings ON job_postings
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_role_evaluations ON role_evaluations
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_evaluation_skips ON evaluation_skips
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_opportunity_reviews ON opportunity_reviews
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_notifications ON notifications
  FOR SELECT TO authenticated USING (
    EXISTS (
      SELECT 1 FROM app_allowed_users allowed
      WHERE lower(allowed.email) = lower(auth.jwt() ->> 'email')
    )
  );

CREATE POLICY owner_read_allowed_users ON app_allowed_users
  FOR SELECT TO authenticated USING (
    lower(email) = lower(auth.jwt() ->> 'email')
  );

REVOKE ALL ON companies FROM anon;
REVOKE ALL ON job_sources FROM anon;
REVOKE ALL ON source_runs FROM anon;
REVOKE ALL ON job_postings FROM anon;
REVOKE ALL ON role_evaluations FROM anon;
REVOKE ALL ON evaluation_skips FROM anon;
REVOKE ALL ON opportunity_reviews FROM anon;
REVOKE ALL ON notifications FROM anon;
REVOKE ALL ON app_allowed_users FROM anon;

GRANT SELECT ON companies TO authenticated;
GRANT SELECT ON job_sources TO authenticated;
GRANT SELECT ON source_runs TO authenticated;
GRANT SELECT ON job_postings TO authenticated;
GRANT SELECT ON role_evaluations TO authenticated;
GRANT SELECT ON evaluation_skips TO authenticated;
GRANT SELECT ON opportunity_reviews TO authenticated;
GRANT SELECT ON notifications TO authenticated;
GRANT SELECT ON app_allowed_users TO authenticated;
GRANT SELECT ON current_calibrated_role_evaluations TO authenticated;
GRANT SELECT ON current_opportunity_evaluations TO authenticated;
