-- Forward migration; Stage 1 checksums and evidence stay unchanged.
DO $$ DECLARE c record; BEGIN
    FOR c IN SELECT conname FROM pg_constraint
        WHERE conrelid='workflow_jobs'::regclass AND contype='c'
          AND (pg_get_constraintdef(oid) LIKE '%state%' OR pg_get_constraintdef(oid) LIKE '%namespace%')
    LOOP EXECUTE format('ALTER TABLE workflow_jobs DROP CONSTRAINT %I',c.conname); END LOOP;
    FOR c IN SELECT conname FROM pg_constraint
        WHERE conrelid='workflow_attempts'::regclass AND contype='c'
          AND pg_get_constraintdef(oid) LIKE '%state%'
    LOOP EXECUTE format('ALTER TABLE workflow_attempts DROP CONSTRAINT %I',c.conname); END LOOP;
END $$;
ALTER TABLE workflow_jobs
    ADD COLUMN action_version integer NOT NULL DEFAULT 1 CHECK (action_version > 0),
    ADD COLUMN approval_required boolean NOT NULL DEFAULT false,
    ADD COLUMN cancel_requested_at timestamptz,
    ADD COLUMN cancelled_by text,
    ADD CONSTRAINT workflow_tenant CHECK (namespace ~ '^[A-Za-z0-9_.-]{1,64}$'),
    ADD CONSTRAINT workflow_states CHECK (state IN ('queued','waiting_approval','running','retry_wait','succeeded','failed','cancelled')),
    ADD CONSTRAINT workflow_lease CHECK ((state='running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (state<>'running' AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)),
    ADD CONSTRAINT workflow_terminal CHECK ((state IN ('succeeded','failed','cancelled'))=(finished_at IS NOT NULL)),
    ADD CONSTRAINT workflow_result CHECK ((state='succeeded')=(result IS NOT NULL)),
    ADD CONSTRAINT workflow_job_tenant UNIQUE(id,namespace);
ALTER TABLE workflow_attempts
    ADD CONSTRAINT workflow_attempt_states CHECK (state IN ('running','succeeded','failed','timed_out','lost','cancelled')),
    ADD CONSTRAINT workflow_attempt_finished CHECK ((state='running')=(finished_at IS NULL));
UPDATE workflow_jobs SET approval_required=true WHERE payload->'request'->>'demo'='effect'
    AND state NOT IN ('succeeded','failed','cancelled');
CREATE OR REPLACE FUNCTION workflow_validate_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state <> NEW.state AND NOT (
        (OLD.state IN ('queued','retry_wait') AND NEW.state IN ('running','waiting_approval','failed','cancelled')) OR
        (OLD.state='waiting_approval' AND NEW.state IN ('queued','failed','cancelled')) OR
        (OLD.state='running' AND NEW.state IN ('succeeded','failed','retry_wait','waiting_approval','cancelled'))
    ) THEN RAISE EXCEPTION 'Invalid workflow state transition'; END IF;
    IF OLD.state IN ('succeeded','failed','cancelled') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Terminal workflow jobs are immutable';
    END IF;
    IF (NEW.payload,NEW.payload_hash,NEW.action_version,NEW.namespace,NEW.approval_required)
       IS DISTINCT FROM (OLD.payload,OLD.payload_hash,OLD.action_version,OLD.namespace,OLD.approval_required)
    THEN RAISE EXCEPTION 'Workflow action and tenant are immutable'; END IF;
    RETURN NEW;
END; $$;

CREATE TABLE workflow_approvals (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    tenant_id text NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    action_hash text NOT NULL,
    action_version integer NOT NULL,
    state text NOT NULL CHECK (state IN ('pending','approved','rejected','expired','consumed','cancelled')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    decided_at timestamptz,
    approver text,
    consumed_at timestamptz,
    UNIQUE(job_id,attempt_number),
    FOREIGN KEY(job_id,tenant_id) REFERENCES workflow_jobs(id,namespace),
    CHECK (state NOT IN ('approved','rejected','consumed') OR approver IS NOT NULL),
    CHECK ((state='consumed')=(consumed_at IS NOT NULL))
);
CREATE INDEX workflow_approvals_tenant ON workflow_approvals(tenant_id,created_at);
CREATE TABLE workflow_budgets (
    tenant_id text PRIMARY KEY,
    limit_units bigint NOT NULL CHECK (limit_units >= 0),
    reserved_units bigint NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    spent_units bigint NOT NULL DEFAULT 0 CHECK (spent_units >= 0)
);
CREATE TABLE workflow_operations (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    tenant_id text NOT NULL,
    attempt_number integer NOT NULL,
    action_hash text NOT NULL,
    state text NOT NULL CHECK (state IN ('reserved','in_flight','succeeded','uncertain','released')),
    reserved_units bigint NOT NULL CHECK (reserved_units >= 0),
    actual_units bigint CHECK (actual_units >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(job_id,attempt_number),
    FOREIGN KEY(job_id,attempt_number) REFERENCES workflow_attempts(job_id,number),
    FOREIGN KEY(job_id,tenant_id) REFERENCES workflow_jobs(id,namespace)
);
CREATE INDEX workflow_operations_tenant ON workflow_operations(tenant_id,created_at);
-- No credentials, example tenants or funded budgets are inserted by migrations.

UPDATE workflow_jobs SET state='waiting_approval' WHERE approval_required AND state IN ('queued','retry_wait');
INSERT INTO workflow_approvals(id,job_id,tenant_id,attempt_number,action_hash,action_version,state,expires_at)
SELECT gen_random_uuid(),id,namespace,attempt_count+1,payload_hash,action_version,'pending',
    LEAST(deadline_at,clock_timestamp()+interval '60 seconds') FROM workflow_jobs WHERE state='waiting_approval';
