-- Owner-applied after review. This changes live reads only; it never deletes
-- postings, evaluations, reviews, applications, or their historical snapshots.
-- The web read layer also checks current watchlist ATS/key before reading.
CREATE OR REPLACE VIEW current_calibrated_role_evaluations
WITH (security_invoker = true) AS
SELECT re.*
FROM role_evaluations re
JOIN job_postings jp ON jp.id = re.job_posting_id
JOIN job_sources js ON js.id = jp.source_id
JOIN companies c ON c.id = jp.company_id
WHERE js.company_id = c.id
  AND lower(js.health_status) NOT IN ('disabled', 'retired')
  AND (js.source_type = 'manual' OR c.enabled = 1)
  AND re.id = (
    SELECT MAX(latest.id)
    FROM role_evaluations latest
    WHERE latest.job_posting_id = re.job_posting_id
      AND latest.model_version LIKE '%|hybrid\_claude\_v4' ESCAPE '\'
      AND latest.model_version NOT ILIKE '%deterministic_fallback%'
      AND COALESCE(
        lower(latest.evaluation_json::jsonb #>> '{provenance,fallback_quality}'),
        'false'
      ) <> 'true'
      AND COALESCE(
        lower(latest.evaluation_json::jsonb #>> '{provenance,is_fallback}'),
        'false'
      ) <> 'true'
  );

-- CREATE OR REPLACE preserves the existing authenticated grant and dependency
-- from current_opportunity_evaluations. Explicitly keep anonymous access closed.
REVOKE ALL ON current_calibrated_role_evaluations FROM PUBLIC, anon;
GRANT SELECT ON current_calibrated_role_evaluations TO authenticated;

-- Append a typed UTC instant for server-side recency filtering before LIMIT.
-- Original source strings remain intact, including historical mixed offsets.
CREATE OR REPLACE VIEW current_opportunity_evaluations
WITH (security_invoker = true) AS
SELECT
  jp.id AS job_id,
  c.id AS company_id,
  c.name AS company,
  c.tier AS company_tier,
  c.enabled AS company_enabled,
  js.id AS source_id,
  js.source_type,
  js.source_key,
  jp.source_job_id,
  jp.canonical_key,
  jp.title,
  jp.locations_json,
  jp.department,
  jp.employment_type,
  jp.description_text,
  jp.source_url,
  jp.posted_at,
  jp.first_seen_at,
  jp.last_seen_at,
  jp.availability_state,
  re.id AS role_evaluation_id,
  re.model_version,
  re.evaluation_json,
  re.created_at AS evaluated_at,
  orev.state AS review_state,
  orev.decision_reason,
  orev.reviewed_at,
  orev.snooze_until,
  CASE WHEN COALESCE(jp.posted_at, jp.first_seen_at) ~ '[T ].*([Zz]|[+-][0-9]{2}(:[0-9]{2}|[0-9]{2}){0,1})$' THEN CAST(COALESCE(jp.posted_at, jp.first_seen_at) AS TIMESTAMP WITH TIME ZONE) ELSE CAST(COALESCE(jp.posted_at, jp.first_seen_at) AS TIMESTAMP) AT TIME ZONE 'UTC' END AS effective_at
FROM job_postings jp
JOIN companies c ON c.id = jp.company_id
JOIN job_sources js ON js.id = jp.source_id
JOIN opportunity_reviews orev ON orev.job_posting_id = jp.id
JOIN current_calibrated_role_evaluations re ON re.job_posting_id = jp.id;

REVOKE ALL ON current_opportunity_evaluations FROM PUBLIC, anon;
GRANT SELECT ON current_opportunity_evaluations TO authenticated;
