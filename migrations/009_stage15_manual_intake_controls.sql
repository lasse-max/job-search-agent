-- Stage 1.5 B-30 follow-up: owner correction controls for pending manual intake.
-- The scanner remains the only evaluator. Browser writes stay behind narrow,
-- owner-gated SECURITY DEFINER functions and cannot touch processing/completed rows.

CREATE OR REPLACE FUNCTION public.remove_manual_intake(
  p_submission_id INTEGER
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  requester_email TEXT := lower(COALESCE((SELECT auth.jwt() ->> 'email'), ''));
  removed_id INTEGER;
BEGIN
  IF (SELECT auth.uid()) IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.app_allowed_users allowed
    WHERE lower(allowed.email) = requester_email
  ) THEN
    RAISE EXCEPTION 'owner access required' USING ERRCODE = '42501';
  END IF;

  DELETE FROM public.manual_intake_submissions AS submission
  WHERE submission.id = p_submission_id
    AND lower(submission.owner_email) = requester_email
    AND submission.status IN ('queued', 'needs_text', 'manual_unscored', 'failed')
  RETURNING submission.id INTO removed_id;

  IF removed_id IS NULL THEN
    RAISE EXCEPTION 'pending manual intake not found or is currently processing'
      USING ERRCODE = '55000';
  END IF;

  RETURN jsonb_build_object('removed', true, 'submission_id', removed_id);
END;
$$;

REVOKE ALL ON FUNCTION public.remove_manual_intake(INTEGER) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.remove_manual_intake(INTEGER) TO authenticated;

CREATE OR REPLACE FUNCTION public.replace_manual_intake_with_url(
  p_submission_id INTEGER,
  p_company TEXT,
  p_title TEXT,
  p_location TEXT DEFAULT NULL,
  p_source_url TEXT DEFAULT NULL,
  p_note TEXT DEFAULT NULL,
  p_destination TEXT DEFAULT 'potential_matches',
  p_propose_watchlist BOOLEAN DEFAULT false
)
RETURNS public.manual_intake_submissions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  requester_email TEXT := lower(COALESCE((SELECT auth.jwt() ->> 'email'), ''));
  destination TEXT := lower(btrim(COALESCE(p_destination, '')));
  prior public.manual_intake_submissions%ROWTYPE;
  replacement public.manual_intake_submissions%ROWTYPE;
BEGIN
  IF (SELECT auth.uid()) IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.app_allowed_users allowed
    WHERE lower(allowed.email) = requester_email
  ) THEN
    RAISE EXCEPTION 'owner access required' USING ERRCODE = '42501';
  END IF;
  IF destination NOT IN ('potential_matches', 'to_apply', 'applied') THEN
    RAISE EXCEPTION 'invalid intake destination' USING ERRCODE = '22023';
  END IF;
  IF length(btrim(COALESCE(p_company, ''))) NOT BETWEEN 1 AND 200
     OR length(btrim(COALESCE(p_title, ''))) NOT BETWEEN 1 AND 300 THEN
    RAISE EXCEPTION 'company and title are required' USING ERRCODE = '22023';
  END IF;
  IF COALESCE(p_source_url, '') !~* '^https?://' THEN
    RAISE EXCEPTION 'URL intake requires http(s)' USING ERRCODE = '22023';
  END IF;
  IF length(COALESCE(p_note, '')) > 4000 THEN
    RAISE EXCEPTION 'note is too long' USING ERRCODE = '22001';
  END IF;

  SELECT submission.* INTO prior
  FROM public.manual_intake_submissions AS submission
  WHERE submission.id = p_submission_id
    AND lower(submission.owner_email) = requester_email
    AND submission.status IN ('queued', 'needs_text', 'manual_unscored', 'failed')
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'pending manual intake not found or is currently processing'
      USING ERRCODE = '55000';
  END IF;

  DELETE FROM public.manual_intake_submissions WHERE id = prior.id;

  INSERT INTO public.manual_intake_submissions (
    owner_email, intake_mode, source_url, jd_text, company, title, location,
    note, destination, propose_watchlist, status
  ) VALUES (
    requester_email,
    'url',
    btrim(p_source_url),
    NULL,
    btrim(p_company),
    btrim(p_title),
    NULLIF(btrim(p_location), ''),
    COALESCE(NULLIF(btrim(p_note), ''), prior.note),
    destination,
    p_propose_watchlist,
    'queued'
  )
  RETURNING * INTO replacement;

  RETURN replacement;
END;
$$;

REVOKE ALL ON FUNCTION public.replace_manual_intake_with_url(
  INTEGER, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN
) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.replace_manual_intake_with_url(
  INTEGER, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, BOOLEAN
) TO authenticated;
