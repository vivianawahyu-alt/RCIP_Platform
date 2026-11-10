export type Role = "REGULATORY_ANALYST" | "COMPLIANCE_OFFICER" | "BUSINESS_CONTROL_OWNER" | "LEGAL_REVIEWER"
  | "COMPLIANCE_MANAGER" | "INTERNAL_AUDITOR" | "EXECUTIVE" | "SYSTEM_ADMINISTRATOR";
export type Me = { username: string; role: Role; user_id: string };
export type User = { id: string; username: string; role: Role };
export type Citation = { provision_version_id: string; canonical_number: string; number_label: string };
export type Doc = { id: string; canonical_number: string; title_id: string; status: string; instrument_type: string; issuer?: string;
  labels?: { dimension: string; value: string; state: string }[];
  created_at?: string;
  // [A1] sumber asal dokumen (registri sumber, FR-RKM-001)
  source?: { id: string; name: string; status: string } | null;
  // [9] extraction_method: "TEXT_LAYER" | "OCR" | "PLAIN_TEXT" (cara teks versi ini diperoleh)
  // [A2] provenans versi: URL asal, nama & ukuran berkas, has_file = berkas asli tersimpan (bisa dibuka)
  versions: { id: string; version_number: number; state: string; effective_date: string; extraction_method?: string;
    origin_url?: string | null; file_name?: string | null; size_bytes?: number | null; has_file?: boolean }[] };
// [A3] satu sumber regulasi pada registri (GET /corpus/sources)
export type Source = { id: string; name: string; category: string; issuer_name: string; base_url: string; url_allow_list: string[];
  status: string; permitted_use_statement?: string | null; citation_requirement_text?: string | null; created_by?: string | null;
  submitted_by?: string | null; approved_by?: string | null; approved_at?: string | null; return_reason?: string | null; documents: number };
// [A4] satu interaksi copilot (log FR-COP-004) beserta tinjauannya (FR-COP-005)
export type CopilotReview = { id: string; state: "PENDING" | "COMPLETED"; requested_by?: string | null; requested_at?: string | null;
  request_note?: string | null; reviewer?: string | null; verdict?: "CONFIRMED" | "CORRECTED" | "REJECTED" | null;
  corrected_text?: string | null; reviewed_at?: string | null };
export type Interaction = { id: string; question: string; user?: string | null; state?: string; confidence: number; low_confidence: boolean;
  retrieved: any[]; template: string; model_id?: string | null; created_at?: string; review?: CopilotReview | null };
export type Obligation = { id: string; state: string; summary: string; deadline: string | null; derived_from_ai: boolean;
  confidence?: number | null; owner_id?: string | null; owner?: string | null; validator?: string | null; approver?: string | null;
  frequency?: string | null; original_text?: string; created_at?: string; citation: Citation;
  supporting_phrases?: string[]; model_id?: string | null; low_confidence?: boolean; reopen_reason?: string | null;
  required_actions?: string[]; ai?: { template: string; model_id: string; schema_valid: boolean; grounding_passed: boolean; confidence: number | null } | null };
export type Risk = { id: string; obligation_id: string; title: string; severity: string; obligation_summary?: string };
export type Control = { id: string; risk_id?: string | null; risk_title?: string | null; title: string; owner_id?: string | null;
  owner?: string | null; obligation_id?: string | null; obligation_ids: string[]; evidence_count: number; evidence_accepted: number;
  evidence_pending: number; source_changed?: boolean; latest_assessment?: string | null; latest_assessment_state?: string | null; latest_assessment_id?: string | null };
export type Evidence = { id: string; filename: string; description?: string | null; sha256: string; size_bytes?: number | null;
  state: string; uploaded_by?: string; uploaded_at?: string; reviewed_by?: string | null; review_rationale?: string | null };
export type Assessment = { id: string; control_id: string; control?: string | null; state: string; result: string;
  design_result: string; operating_result: string; design_rationale: string; operating_rationale: string;
  assessed_by?: string; assessed_by_id?: string; assessed_at?: string; submitted_by?: string | null; signed_off_by?: string | null;
  signed_off_at?: string | null; return_reason?: string | null };
export type Action = { id: string; description: string; expected_outcome?: string | null; owner_id?: string | null; owner?: string | null;
  state: string; due_date: string; original_due_date: string; extension_history: { from: string; to: string; reason: string; at: string }[];
  overdue: boolean; completed_at?: string | null; completion_note?: string | null; cancelled_reason?: string | null; evidence: Evidence[] };
export type Finding = { id: string; title: string; description: string; kind: string; source_type: string; severity: string; state: string;
  owner_id?: string | null; owner?: string | null; raised_by?: string | null; raised_by_id?: string | null; created_at: string; age_days: number;
  target_closure_date?: string | null; overdue: boolean; overdue_actions: number;
  obligation?: { id: string; summary: string; state: string; citation: Citation } | null; control?: { id: string; title: string } | null;
  assessment_id?: string | null; closure: { submitted_by?: string | null; submitted_at?: string | null; closed_by?: string | null; closed_at?: string | null; rationale?: string | null };
  risk_acceptance?: { rationale: string; accepted_by?: string | null; review_date?: string | null } | null; reopened_count: number;
  actions: Action[]; action_count?: number; approvals?: any[]; timeline?: any[] };