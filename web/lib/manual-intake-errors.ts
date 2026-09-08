export type IntakeRpcError = { code?: string; message: string };

export function intakeActionError(error: IntakeRpcError, action: "remove" | "replace" | "queue") {
  if (error.code === "PGRST202" || error.code === "42883") {
    return "This control needs a database update before it can work. Your role has been kept.";
  }
  if (error.code === "42501") {
    return "Owner access could not be verified. Sign in again and retry.";
  }
  if (error.code === "55000") {
    return "This role is processing or has already changed. Refresh the page to see its status.";
  }
  return `Could not ${action} this role. Please retry; the submission has not been changed.`;
}

export function intakeEvaluationError(error: string | null) {
  if (!error) return null;
  if (error.includes("credit balance")) return "Evaluation is paused because the model account needs credit.";
  if (error.includes("job_text_too_long") || error.includes("model context")) {
    return "The page was too large to evaluate. Submit the job description text only.";
  }
  if (error.includes("HTTP 400") || error.includes("400 Bad Request")) {
    return "The evaluation service rejected this request. Your role is saved, but has not been scored.";
  }
  if (error.includes("LLMProviderError") || error.includes("claude_")) {
    return "The evaluation service could not score this role. Your submission is still saved.";
  }
  if (error.includes("url_") || error.includes("ManualExtractionError")) {
    return "The job page could not be read. Submit the job description text instead.";
  }
  return "This role could not be processed. Your submission is still saved.";
}
