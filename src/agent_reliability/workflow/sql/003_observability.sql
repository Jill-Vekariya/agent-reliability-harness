-- Observability is separate from the immutable request/idempotency payload.
ALTER TABLE workflow_jobs
    ADD COLUMN request_id text CHECK (request_id ~ '^[a-f0-9]{32}$'),
    ADD COLUMN trace_id text CHECK (trace_id ~ '^[a-f0-9]{32}$'),
    ADD COLUMN parent_span_id text CHECK (parent_span_id ~ '^[a-f0-9]{16}$'),
    ADD CONSTRAINT workflow_trace_pair CHECK ((trace_id IS NULL)=(parent_span_id IS NULL));
CREATE FUNCTION workflow_context_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.request_id,NEW.trace_id,NEW.parent_span_id)
       IS DISTINCT FROM (OLD.request_id,OLD.trace_id,OLD.parent_span_id)
    THEN RAISE EXCEPTION 'Workflow observability context is immutable'; END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER workflow_context BEFORE UPDATE ON workflow_jobs
    FOR EACH ROW EXECUTE FUNCTION workflow_context_immutable();
