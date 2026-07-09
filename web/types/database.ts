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
        Relationships: [];
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
        Relationships: [];
      };
    };
    Tables: {
      companies: {
        Row: {
          id: number;
          name: string;
          tier: number;
          enabled: number;
          warm_path: number;
          notes: string | null;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [];
      };
      evaluation_skips: {
        Row: {
          id: number;
          job_posting_id: number;
          input_hash: string;
          reason: string;
          created_at: string;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [
          {
            foreignKeyName: "evaluation_skips_job_posting_id_fkey";
            columns: ["job_posting_id"];
            isOneToOne: false;
            referencedRelation: "job_postings";
            referencedColumns: ["id"];
          }
        ];
      };
      job_postings: {
        Row: {
          id: number;
          company_id: number;
          source_id: number;
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
          raw_payload_hash: string;
          availability_state: string;
          missing_successful_scan_count: number;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [
          {
            foreignKeyName: "job_postings_company_id_fkey";
            columns: ["company_id"];
            isOneToOne: false;
            referencedRelation: "companies";
            referencedColumns: ["id"];
          }
        ];
      };
      source_runs: {
        Row: {
          id: number;
          job_source_id: number;
          started_at: string;
          finished_at: string;
          status: string;
          http_status: number | null;
          fetched_count: number;
          new_count: number;
          changed_count: number;
          retry_count: number;
          error_summary: string | null;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [];
      };
    };
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
