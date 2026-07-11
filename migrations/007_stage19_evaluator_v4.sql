-- Stage 1.9 profile clean-up: advance calibrated reads to the corrected profile.

CREATE OR REPLACE VIEW current_calibrated_role_evaluations
WITH (security_invoker = true) AS
SELECT re.*
FROM role_evaluations re
WHERE re.id = (
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
