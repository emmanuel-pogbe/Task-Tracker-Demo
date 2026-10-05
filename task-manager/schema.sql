CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL CHECK (length(trim(title)) > 0 AND length(title) <= 200),
    created_at  TEXT    NOT NULL,                      -- UTC, YYYY-MM-DDTHH:MM:SSZ
    updated_at  TEXT    NOT NULL,                      -- UTC, YYYY-MM-DDTHH:MM:SSZ
    due_at      TEXT    NOT NULL,                      -- UTC, YYYY-MM-DDTHH:MM:SSZ
    status      TEXT    NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'done')),
    is_overdue  INTEGER DEFAULT NULL                   -- NULL = not overdue, 1 = overdue
);

CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_due_at     ON tasks (due_at);