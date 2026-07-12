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
      applications: {
        Row: {
          id: number;
          company: string;
          role: string;
          location: string;
          url: string | null;
          stage:
            | "preparing"
            | "applied"
            | "recruiter_screen"
            | "interviewing"
            | "final_round"
            | "offer"
            | "rejected"
            | "withdrawn";
          applied_at: string;
          applied_calendar_week: number;
          next_action: string | null;
          due: string | null;
          contact: string | null;
          salary: string | null;
          notes: string | null;
          source_posting_id: number;
          eval_snapshot_json: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [
          {
            foreignKeyName: "applications_source_posting_id_fkey";
            columns: ["source_posting_id"];
            isOneToOne: true;
            referencedRelation: "job_postings";
            referencedColumns: ["id"];
          }
        ];
      };
      application_events: {
        Row: {
          id: number;
          application_id: number;
          actor: string;
          occurred_at: string;
          previous_stage: string | null;
          new_stage: string;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [
          {
            foreignKeyName: "application_events_application_id_fkey";
            columns: ["application_id"];
            isOneToOne: false;
            referencedRelation: "applications";
            referencedColumns: ["id"];
          }
        ];
      };
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
      job_sources: {
        Row: {
          id: number;
          company_id: number;
          source_type: string;
          source_key: string;
          source_url: string;
          parser_version: string;
          health_status: string;
          last_success_at: string | null;
          expected_volume_min: number | null;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [
          {
            foreignKeyName: "job_sources_company_id_fkey";
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
      manual_intake_submissions: {
        Row: {
          id: number;
          owner_email: string;
          intake_mode: "url" | "text" | "manual";
          source_url: string | null;
          jd_text: string | null;
          company: string;
          title: string;
          location: string | null;
          note: string | null;
          destination: "potential_matches" | "to_apply" | "applied";
          propose_watchlist: boolean;
          status: "queued" | "processing" | "needs_text" | "manual_unscored" | "completed" | "failed";
          job_posting_id: number | null;
          error_summary: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: Record<string, unknown>;
        Update: Record<string, unknown>;
        Relationships: [];
      };
    };
    Functions: {
      change_application_stage: {
        Args: { p_application_id: number; p_new_stage: string };
        Returns: Json;
      };
      mark_application_applied: {
        Args: { p_job_posting_id: number; p_applied_at?: string };
        Returns: Json;
      };
      mark_opportunity_interested: {
        Args: { p_job_posting_id: number; p_note?: string | null };
        Returns: Json;
      };
      remove_opportunity_interest: {
        Args: { p_job_posting_id: number };
        Returns: Json;
      };
      update_application_details: {
        Args: {
          p_application_id: number;
          p_next_action: string;
          p_due: string | null;
          p_contact: string;
          p_salary: string;
          p_notes: string;
        };
        Returns: Json;
      };
      submit_manual_intake: {
        Args: {
          p_intake_mode: string;
          p_company: string;
          p_title: string;
          p_location?: string | null;
          p_source_url?: string | null;
          p_jd_text?: string | null;
          p_note?: string | null;
          p_destination?: string;
          p_propose_watchlist?: boolean;
        };
        Returns: Json;
      };
    };
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
