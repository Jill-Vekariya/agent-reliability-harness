CREATE TABLE workflow_jobs (
    id uuid PRIMARY KEY,
    namespace text NOT NULL CHECK (namespace = 'local-demo'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    payload_hash text NOT NULL CHECK (length(payload_hash) = 64),
    payload jsonb NOT NULL,
    state text NOT NULL CHECK (state IN ('queued','running','retry_wait','succeeded','failed')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
    attempt_seconds double precision NOT NULL CHECK (attempt_seconds BETWEEN 1 AND 600),
    backoff_seconds double precision NOT NULL CHECK (backoff_seconds > 0 AND backoff_seconds <= 5),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    deadline_at timestamptz NOT NULL,
    next_run_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    result jsonb,
    error_code text,
    UNIQUE(namespace, idempotency_key),
    CHECK (attempt_count <= max_attempts),
    CHECK ((state = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (state <> 'running' AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)),
    CHECK ((state IN ('succeeded','failed')) = (finished_at IS NOT NULL)),
    CHECK ((state = 'succeeded') = (result IS NOT NULL)),
    CHECK (deadline_at > created_at)
);
CREATE INDEX workflow_jobs_due ON workflow_jobs(next_run_at,created_at,id)
    WHERE state IN ('queued','retry_wait');
CREATE INDEX workflow_jobs_leases ON workflow_jobs(lease_expires_at)
    WHERE state = 'running';

CREATE TABLE workflow_attempts (
    job_id uuid NOT NULL REFERENCES workflow_jobs(id),
    number integer NOT NULL CHECK (number > 0),
    token uuid NOT NULL UNIQUE,
    worker_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('running','succeeded','failed','timed_out','lost')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    error_code text,
    result jsonb,
    stale_result_rejections integer NOT NULL DEFAULT 0 CHECK (stale_result_rejections >= 0),
    last_rejection_at timestamptz,
    PRIMARY KEY(job_id,number),
    CHECK ((state = 'running') = (finished_at IS NULL))
);

CREATE FUNCTION workflow_validate_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state <> NEW.state AND NOT (
        (OLD.state = 'queued' AND NEW.state IN ('running','failed')) OR
        (OLD.state = 'retry_wait' AND NEW.state IN ('running','failed')) OR
        (OLD.state = 'running' AND NEW.state IN ('succeeded','failed','retry_wait'))
    ) THEN
        RAISE EXCEPTION 'Invalid workflow state transition';
    END IF;
    IF OLD.state IN ('succeeded','failed') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Terminal workflow jobs are immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER workflow_job_transition BEFORE UPDATE ON workflow_jobs
FOR EACH ROW EXECUTE FUNCTION workflow_validate_transition();
