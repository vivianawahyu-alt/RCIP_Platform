"""001_initial_schema — 3 skema (platform, corpus, compliance), FK RESTRICT, SoD, trigger imutabilitas

Revision ID: 001_initial_schema
"""
from alembic import op

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS platform",
    "CREATE SCHEMA IF NOT EXISTS corpus",
    "CREATE SCHEMA IF NOT EXISTS compliance",

    # ---------------- platform ----------------
    """CREATE TABLE platform.app_user (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        username text NOT NULL UNIQUE,
        email text NOT NULL UNIQUE,
        hashed_password text NOT NULL,
        role text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE platform.audit_event (
        id bigserial PRIMARY KEY,
        actor_type text NOT NULL,
        actor_id uuid REFERENCES platform.app_user(id),
        action text NOT NULL,
        object_type text NOT NULL,
        object_id uuid,
        before_state jsonb,
        after_state jsonb,
        correlation_id uuid NOT NULL,
        occurred_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE platform.outbox (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        correlation_id uuid NOT NULL,
        occurred_at timestamptz NOT NULL DEFAULT now(),
        delivered_at timestamptz,
        attempts int NOT NULL DEFAULT 0)""",
    """CREATE TABLE platform.approval (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        object_type text NOT NULL,
        object_id uuid NOT NULL,
        control_point smallint NOT NULL,
        maker_id uuid NOT NULL REFERENCES platform.app_user(id),
        last_editor_id uuid NOT NULL REFERENCES platform.app_user(id),
        checker_id uuid NOT NULL REFERENCES platform.app_user(id),
        outcome text NOT NULL,
        reason text,
        object_state_snapshot jsonb NOT NULL,
        decided_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_sod_maker CHECK (checker_id <> maker_id),
        CONSTRAINT ck_sod_editor CHECK (checker_id <> last_editor_id))""",
    """CREATE TABLE platform.ai_call_log (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        template_name text NOT NULL,
        template_version text NOT NULL,
        model_id text NOT NULL,
        prompt_rendered text NOT NULL,
        raw_response text,
        schema_valid boolean NOT NULL,
        grounding_passed boolean NOT NULL,
        confidence numeric(3,2),
        created_at timestamptz NOT NULL DEFAULT now())""",

    # ---------------- corpus ----------------
    """CREATE TABLE corpus.regulatory_source (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        name text NOT NULL UNIQUE,
        category text NOT NULL,
        issuer_name text NOT NULL,
        base_url text NOT NULL,
        permitted_use_statement text,
        status text NOT NULL DEFAULT 'DRAFT')""",
    """CREATE TABLE corpus.document (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        source_id uuid NOT NULL REFERENCES corpus.regulatory_source(id) ON DELETE RESTRICT,
        canonical_number text NOT NULL UNIQUE,
        instrument_type text NOT NULL,
        issuer text NOT NULL,
        title_id text NOT NULL,
        status text NOT NULL DEFAULT 'DRAFT')""",
    """CREATE TABLE corpus.document_version (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id uuid NOT NULL REFERENCES corpus.document(id) ON DELETE RESTRICT,
        version_number int NOT NULL,
        sha256 varchar(64) NOT NULL,
        origin_url text NOT NULL,
        canonical_text_ref text NOT NULL,
        effective_date date NOT NULL,
        state text NOT NULL DEFAULT 'PARSING',
        is_partial boolean NOT NULL DEFAULT false,
        UNIQUE (document_id, version_number))""",
    """CREATE TABLE corpus.provision (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id uuid NOT NULL REFERENCES corpus.document(id) ON DELETE RESTRICT,
        provision_key text NOT NULL,
        provision_type text NOT NULL,
        number_label text NOT NULL,
        hierarchical_path text NOT NULL,
        UNIQUE (document_id, provision_key))""",
    """CREATE TABLE corpus.provision_version (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        provision_id uuid NOT NULL REFERENCES corpus.provision(id) ON DELETE RESTRICT,
        document_version_id uuid NOT NULL REFERENCES corpus.document_version(id) ON DELETE RESTRICT,
        sequence int NOT NULL,
        text text NOT NULL,
        segmentation_confidence numeric(3,2) NOT NULL DEFAULT 0.85,
        corrected_by_human boolean NOT NULL DEFAULT false,
        text_search tsvector GENERATED ALWAYS AS (to_tsvector('indonesian', text)) STORED,
        UNIQUE (provision_id, document_version_id))""",
    "CREATE INDEX ix_pv_text_search ON corpus.provision_version USING gin(text_search)",
    """CREATE TABLE corpus.change_set (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        base_version_id uuid NOT NULL REFERENCES corpus.document_version(id) ON DELETE RESTRICT,
        new_version_id uuid NOT NULL REFERENCES corpus.document_version(id) ON DELETE RESTRICT,
        created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE corpus.change (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        change_set_id uuid NOT NULL REFERENCES corpus.change_set(id) ON DELETE RESTRICT,
        provision_id uuid NOT NULL REFERENCES corpus.provision(id) ON DELETE RESTRICT,
        base_pv_id uuid REFERENCES corpus.provision_version(id) ON DELETE RESTRICT,
        new_pv_id uuid REFERENCES corpus.provision_version(id) ON DELETE RESTRICT,
        change_type text NOT NULL,
        similarity numeric(5,4),
        is_material boolean NOT NULL DEFAULT false,
        diff_html text)""",

    # ---------------- compliance ----------------
    """CREATE TABLE compliance.organisation_profile (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_name text NOT NULL,
        entity_type text NOT NULL,
        licenses jsonb NOT NULL DEFAULT '[]',
        business_lines jsonb NOT NULL DEFAULT '[]')""",
    """CREATE TABLE compliance.applicability_decision (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        target_version_id uuid NOT NULL REFERENCES corpus.document_version(id) ON DELETE RESTRICT,
        profile_id uuid NOT NULL REFERENCES compliance.organisation_profile(id) ON DELETE RESTRICT,
        decision_value text NOT NULL,
        reason_text text NOT NULL,
        relied_upon_attributes jsonb NOT NULL DEFAULT '{}',
        maker_id uuid NOT NULL REFERENCES platform.app_user(id),
        approver_id uuid REFERENCES platform.app_user(id),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_applicability_sod CHECK (approver_id IS NULL OR approver_id <> maker_id))""",
    """CREATE TABLE compliance.obligation (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        applicability_decision_id uuid NOT NULL REFERENCES compliance.applicability_decision(id) ON DELETE RESTRICT,
        primary_citation_id uuid NOT NULL REFERENCES corpus.provision_version(id) ON DELETE RESTRICT,
        original_text text NOT NULL,
        plain_language_summary text,
        required_actions jsonb NOT NULL DEFAULT '[]',
        frequency text,
        deadline_expression text,
        required_evidence text,
        confidence numeric(3,2),
        derived_from_ai boolean NOT NULL DEFAULT true,
        owner_id uuid REFERENCES platform.app_user(id),
        validator_id uuid REFERENCES platform.app_user(id),
        approver_id uuid REFERENCES platform.app_user(id),
        state text NOT NULL DEFAULT 'AI_DRAFT',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_obligation_sod CHECK (approver_id IS NULL OR approver_id <> validator_id),
        CONSTRAINT ck_active_needs_owner CHECK (state NOT IN ('ACTIVE','PENDING_APPROVAL') OR owner_id IS NOT NULL))""",
    """CREATE TABLE compliance.risk (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        obligation_id uuid NOT NULL REFERENCES compliance.obligation(id) ON DELETE RESTRICT,
        title text NOT NULL,
        severity text NOT NULL DEFAULT 'MEDIUM')""",
    """CREATE TABLE compliance.control (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        risk_id uuid REFERENCES compliance.risk(id) ON DELETE RESTRICT,
        title text NOT NULL,
        owner_id uuid REFERENCES platform.app_user(id))""",
    """CREATE TABLE compliance.obligation_control_map (
        obligation_id uuid NOT NULL REFERENCES compliance.obligation(id) ON DELETE RESTRICT,
        control_id uuid NOT NULL REFERENCES compliance.control(id) ON DELETE RESTRICT,
        PRIMARY KEY (obligation_id, control_id))""",
    """CREATE TABLE compliance.evidence (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        control_id uuid NOT NULL REFERENCES compliance.control(id) ON DELETE RESTRICT,
        filename text NOT NULL,
        object_key text NOT NULL,
        sha256 varchar(64) NOT NULL,
        uploaded_by uuid REFERENCES platform.app_user(id),
        uploaded_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE compliance.assessment (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        control_id uuid NOT NULL REFERENCES compliance.control(id) ON DELETE RESTRICT,
        result text NOT NULL,
        notes text,
        assessed_by uuid REFERENCES platform.app_user(id),
        assessed_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE compliance.finding (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        obligation_id uuid NOT NULL REFERENCES compliance.obligation(id) ON DELETE RESTRICT,
        kind text NOT NULL,
        description text NOT NULL,
        state text NOT NULL DEFAULT 'OPEN',
        created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE compliance.remediation_action (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        finding_id uuid NOT NULL REFERENCES compliance.finding(id) ON DELETE RESTRICT,
        description text NOT NULL,
        due_date date NOT NULL,
        owner_id uuid REFERENCES platform.app_user(id),
        state text NOT NULL DEFAULT 'OPEN')""",
    """CREATE TABLE compliance.compliance_report (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        title text NOT NULL,
        payload jsonb NOT NULL,
        state text NOT NULL DEFAULT 'ISSUED',
        created_by uuid REFERENCES platform.app_user(id),
        created_at timestamptz NOT NULL DEFAULT now())""",

    # ---------------- trigger imutabilitas & pagar pengaman ----------------
    """CREATE FUNCTION platform.forbid_frozen_version() RETURNS trigger AS $$
    BEGIN
        IF current_setting('rcip.seeding', true) = 'on' THEN
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END IF;
        IF TG_OP = 'DELETE' THEN
            IF OLD.state IN ('PUBLISHED','WITHDRAWN') THEN
                RAISE EXCEPTION 'VERSION_IMMUTABLE: published version % cannot be deleted', OLD.id USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END IF;
        IF OLD.state IN ('PUBLISHED','WITHDRAWN') AND NEW.state IS DISTINCT FROM 'WITHDRAWN' THEN
            RAISE EXCEPTION 'VERSION_IMMUTABLE: published version % cannot be modified', OLD.id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_dv_frozen BEFORE UPDATE OR DELETE ON corpus.document_version
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_frozen_version()""",

    """CREATE FUNCTION platform.forbid_frozen_provision_version() RETURNS trigger AS $$
    DECLARE parent_state text;
    BEGIN
        IF current_setting('rcip.seeding', true) = 'on' THEN
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END IF;
        SELECT state INTO parent_state FROM corpus.document_version WHERE id = OLD.document_version_id;
        IF parent_state IN ('PUBLISHED','WITHDRAWN') THEN
            RAISE EXCEPTION 'VERSION_IMMUTABLE: provision_version % belongs to a frozen version', OLD.id USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_pv_frozen BEFORE UPDATE OR DELETE ON corpus.provision_version
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_frozen_provision_version()""",

    """CREATE FUNCTION platform.forbid_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'APPEND_ONLY: % on %.% is not allowed', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME USING ERRCODE = '23514';
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON platform.audit_event
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_append_only()""",
    """CREATE TRIGGER trg_approval_append_only BEFORE UPDATE OR DELETE ON platform.approval
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_append_only()""",

    """CREATE FUNCTION compliance.block_ai_draft_mapping() RETURNS trigger AS $$
    DECLARE ob_state text;
    BEGIN
        SELECT state INTO ob_state FROM compliance.obligation WHERE id = NEW.obligation_id;
        IF ob_state IN ('AI_DRAFT','IN_VALIDATION') THEN
            RAISE EXCEPTION 'AI_DRAFT_BLOCKED: obligation % belum divalidasi manusia', NEW.obligation_id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_block_ai_draft BEFORE INSERT ON compliance.obligation_control_map
        FOR EACH ROW EXECUTE FUNCTION compliance.block_ai_draft_mapping()""",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for schema in ("compliance", "corpus", "platform"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
