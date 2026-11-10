// DIBANGKITKAN dari app/shared/rbac_matrix.py — jangan diedit tangan. Jalankan: python scripts/gen_permissions_ts.py
export const MATRIX: Record<string, Record<string, string>> = {
  "source_registry": {
    "REGULATORY_ANALYST": "CRU",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "CRUD"
  },
  "ingestion": {
    "REGULATORY_ANALYST": "CRUX",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "RX"
  },
  "document_version": {
    "REGULATORY_ANALYST": "CR",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "provision_correction": {
    "REGULATORY_ANALYST": "CRU",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "relationship": {
    "REGULATORY_ANALYST": "CRUD",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "RU",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "doc_status": {
    "REGULATORY_ANALYST": "CRU",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "taxonomy": {
    "REGULATORY_ANALYST": "CRU",
    "COMPLIANCE_OFFICER": "CRU",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "CRUD"
  },
  "corpus_search": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "R",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "change_detection": {
    "REGULATORY_ANALYST": "XR",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "XR"
  },
  "change_review": {
    "REGULATORY_ANALYST": "CRU",
    "COMPLIANCE_OFFICER": "RU",
    "LEGAL_REVIEWER": "RU",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "org_profile": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "applicability": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "CRU",
    "LEGAL_REVIEWER": "RU",
    "COMPLIANCE_MANAGER": "A",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "obligation": {
    "REGULATORY_ANALYST": "CR",
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "RU",
    "COMPLIANCE_MANAGER": "A",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "obligation_owner": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "risk": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "control_library": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "control_owner": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "assessment_campaign": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R"
  },
  "self_assessment": {
    "COMPLIANCE_OFFICER": "RU",
    "BUSINESS_CONTROL_OWNER": "CRU",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "assessment_conclusion": {
    "COMPLIANCE_OFFICER": "CRU",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "A",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "evidence_request": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "evidence_upload": {
    "COMPLIANCE_OFFICER": "CR",
    "BUSINESS_CONTROL_OWNER": "CR",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "evidence_access": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "R",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "finding": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "R",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "remediation": {
    "COMPLIANCE_OFFICER": "CRU",
    "BUSINESS_CONTROL_OWNER": "RUX",
    "COMPLIANCE_MANAGER": "RA",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "finding_closure": {
    "COMPLIANCE_OFFICER": "CR",
    "COMPLIANCE_MANAGER": "A",
    "INTERNAL_AUDITOR": "R"
  },
  "finding_reopen": {
    "COMPLIANCE_OFFICER": "CR",
    "COMPLIANCE_MANAGER": "X",
    "INTERNAL_AUDITOR": "R"
  },
  "copilot_query": {
    "REGULATORY_ANALYST": "XR",
    "COMPLIANCE_OFFICER": "XR",
    "BUSINESS_CONTROL_OWNER": "XR",
    "LEGAL_REVIEWER": "XR",
    "COMPLIANCE_MANAGER": "XR",
    "INTERNAL_AUDITOR": "XR",
    "EXECUTIVE": "XR",
    "SYSTEM_ADMINISTRATOR": "XR"
  },
  "copilot_promote": {
    "REGULATORY_ANALYST": "CR",
    "COMPLIANCE_OFFICER": "CR",
    "LEGAL_REVIEWER": "CR",
    "COMPLIANCE_MANAGER": "R"
  },
  "dashboard": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "R",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "report_draft": {
    "COMPLIANCE_OFFICER": "CRU",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R"
  },
  "report_issue": {
    "COMPLIANCE_MANAGER": "A",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R"
  },
  "report_published": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "R",
    "BUSINESS_CONTROL_OWNER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "EXECUTIVE": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "audit_trail": {
    "REGULATORY_ANALYST": "R",
    "COMPLIANCE_OFFICER": "R",
    "LEGAL_REVIEWER": "R",
    "COMPLIANCE_MANAGER": "R",
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "R"
  },
  "user_admin": {
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "CRUD"
  },
  "system_config": {
    "INTERNAL_AUDITOR": "R",
    "SYSTEM_ADMINISTRATOR": "CRUDX"
  }
};

/** Apakah peran boleh melakukan aksi (C/R/U/D/A/X) pada kapabilitas? 'A' mencakup 'R'. */
export const canDo = (role: string, cap: string, letter: string): boolean => {
  const cell = MATRIX[cap]?.[role] || "";
  return cell.includes(letter) || (letter === "R" && cell.includes("A"));
};
