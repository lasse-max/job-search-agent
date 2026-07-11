-- Prevent stale-evaluation backfills from repeatedly selecting roles that the
-- current evaluator has already rejected at the deterministic relevance gate.

ALTER TABLE evaluation_skips
  ADD COLUMN IF NOT EXISTS evaluator_version TEXT;

CREATE INDEX IF NOT EXISTS idx_evaluation_skips_evaluator
  ON evaluation_skips(job_posting_id, evaluator_version);
