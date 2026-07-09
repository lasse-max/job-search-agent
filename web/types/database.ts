export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type Database = {
  public: {
    Views: {
      current_opportunity_evaluations: {
        Row: {
          job_id: number;
          company_id: number;
          company: string;
          company_tier: number;
          company_enabled: number;
          source_id: number;
          source_type: string;
          source_key: string;
          source_job_id: string;
          canonical_key: string;
          title: string;
          locations_json: string;
          department: string | null;
          employment_type: string | null;
          description_text: string;
          source_url: string;
          posted_at: string | null;
          first_seen_at: string;
          last_seen_at: string;
          availability_state: string;
          role_evaluation_id: number;
          model_version: string;
          evaluation_json: string;
          evaluated_at: string;
          review_state: string;
          decision_reason: string | null;
          reviewed_at: string | null;
          snooze_until: string | null;
        };
        Insert: never;
        Update: never;
      };
      current_calibrated_role_evaluations: {
        Row: {
          id: number;
          job_posting_id: number;
          profile_version_id: string;
          location_policy_version_id: string;
          prompt_version: string;
          model_version: string;
          input_hash: string;
          evaluation_json: string;
          created_at: string;
        };
        Insert: never;
        Update: never;
      };
    };
    Tables: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
