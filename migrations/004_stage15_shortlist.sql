-- Stage 1.5 A4: owner-gated shortlist state and pipeline transition.

CREATE OR REPLACE FUNCTION public.mark_opportunity_interested(
  p_job_posting_id INTEGER,
  p_note TEXT DEFAULT NULL
)
RETURNS public.opportunity_reviews
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  review_row public.opportunity_reviews%ROWTYPE;
  cleaned_note TEXT := NULLIF(btrim(p_note), '');
BEGIN
  IF (SELECT auth.uid()) IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.app_allowed_users allowed
    WHERE lower(allowed.email) = lower((SELECT auth.jwt() ->> 'email'))
  ) THEN
    RAISE EXCEPTION 'owner access required' USING ERRCODE = '42501';
  END IF;

  IF cleaned_note IS NOT NULL AND length(cleaned_note) > 1000 THEN
    RAISE EXCEPTION 'shortlist note is too long' USING ERRCODE = '22001';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.current_opportunity_evaluations evaluation
    WHERE evaluation.job_id = p_job_posting_id
      AND evaluation.availability_state = 'open'
  ) THEN
    RAISE EXCEPTION 'posting has no open current calibrated evaluation'
      USING ERRCODE = 'P0002';
  END IF;

  INSERT INTO public.opportunity_reviews (
    job_posting_id,
    state,
    decision_reason,
    reviewed_at,
    snooze_until
  )
  VALUES (
    p_job_posting_id,
    'interested',
    cleaned_note,
    now()::TEXT,
    NULL
  )
  ON CONFLICT (job_posting_id) DO UPDATE SET
    state = 'interested',
    decision_reason = EXCLUDED.decision_reason,
    reviewed_at = EXCLUDED.reviewed_at,
    snooze_until = NULL
  RETURNING * INTO review_row;

  RETURN review_row;
END;
$$;

CREATE OR REPLACE FUNCTION public.remove_opportunity_interest(
  p_job_posting_id INTEGER
)
RETURNS public.opportunity_reviews
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  review_row public.opportunity_reviews%ROWTYPE;
BEGIN
  IF (SELECT auth.uid()) IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.app_allowed_users allowed
    WHERE lower(allowed.email) = lower((SELECT auth.jwt() ->> 'email'))
  ) THEN
    RAISE EXCEPTION 'owner access required' USING ERRCODE = '42501';
  END IF;

  UPDATE public.opportunity_reviews
  SET
    state = 'new',
    decision_reason = NULL,
    reviewed_at = NULL,
    snooze_until = NULL
  WHERE job_posting_id = p_job_posting_id
    AND state = 'interested'
  RETURNING * INTO review_row;

  IF review_row.id IS NULL THEN
    RAISE EXCEPTION 'posting is not shortlisted' USING ERRCODE = 'P0002';
  END IF;

  RETURN review_row;
END;
$$;

CREATE OR REPLACE FUNCTION private.close_shortlist_on_application()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF (SELECT auth.uid()) IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.app_allowed_users allowed
    WHERE lower(allowed.email) = lower((SELECT auth.jwt() ->> 'email'))
  ) THEN
    RAISE EXCEPTION 'owner access required' USING ERRCODE = '42501';
  END IF;

  UPDATE public.opportunity_reviews
  SET
    state = 'approved',
    decision_reason = NULL,
    reviewed_at = now()::TEXT,
    snooze_until = NULL
  WHERE job_posting_id = NEW.source_posting_id
    AND state = 'interested';
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS application_closes_shortlist ON public.applications;
CREATE TRIGGER application_closes_shortlist
AFTER INSERT ON public.applications
FOR EACH ROW EXECUTE FUNCTION private.close_shortlist_on_application();

REVOKE EXECUTE ON FUNCTION private.close_shortlist_on_application() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.mark_opportunity_interested(INTEGER, TEXT)
  FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.remove_opportunity_interest(INTEGER)
  FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.mark_opportunity_interested(INTEGER, TEXT)
  TO authenticated;
GRANT EXECUTE ON FUNCTION public.remove_opportunity_interest(INTEGER)
  TO authenticated;
