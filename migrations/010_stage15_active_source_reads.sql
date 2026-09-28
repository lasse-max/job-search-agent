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
