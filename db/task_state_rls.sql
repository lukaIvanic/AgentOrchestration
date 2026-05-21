-- PostgreSQL row-level workspace isolation for task_state.
-- The application must set app.workspace_id before accessing task state:
--   SET LOCAL app.workspace_id = '<workspace-id>';

CREATE TABLE IF NOT EXISTS task_state (
    workspace_id text NOT NULL,
    task_id text NOT NULL,
    state text NOT NULL,
    retries integer NOT NULL DEFAULT 0,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, task_id)
);

ALTER TABLE task_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_state FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS task_state_workspace_scope ON task_state;
CREATE POLICY task_state_workspace_scope ON task_state
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
