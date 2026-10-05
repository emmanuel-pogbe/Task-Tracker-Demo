# PRD: Simple Task Manager

**Stack:** Python 3.10+ · Flask · SQLite (stdlib `sqlite3`) · APScheduler · plain HTML/CSS/JS
**Users:** Single user, no login.
**Audience of this document:** an implementing AI agent. Follow it literally. Copy the code blocks as written, then run the verification steps.

---

## 1. Agent Rules (read first)

1. Implement **only** what is in this document. Do not add features, auth, ORMs, frameworks, or build tools.
2. Allowed dependencies: `Flask`, `APScheduler` (v3 only), `pytest`. Nothing else.
3. Use the stdlib `sqlite3` module. **Never** use an ORM. **Always** use `?` placeholders for values (never f-strings with user input in SQL).
4. All timestamps are **UTC strings** in the exact format `YYYY-MM-DDTHH:MM:SSZ` (see section 5).
5. Build in the order given in section 12. Run each "Done when" check before moving on.
6. If something is unclear, pick the simplest option that satisfies the acceptance criteria in section 13.

---

## 2. Product Summary

A single-page web app where one user creates tasks with a due date, sees them in a list, and marks them done. A background scheduler flags tasks whose due date has passed as overdue and prints a message to the console. The page refreshes itself every 5 minutes. The user can export tasks in a date range as a CSV file.

### Decisions already made (do not ask, do not change)

| Topic | Decision |
|---|---|
| Due date input | `datetime-local` picker plus quick buttons: **+1 day, +1 week, +2 weeks**. (No natural-language parsing. "Due in 2 weeks" = click **+2 weeks**.) |
| Time storage | UTC in DB. Browser converts local time to UTC before sending, and UTC to local time for display. |
| Overdue column | Nullable integer. `NULL` = not flagged. `1` = flagged overdue by the scheduler. Never write `0`. |
| Overdue display | Frontend uses `is_overdue` from the API only. It does **not** compare dates itself. |
| Done tasks | A done task is never flagged by the scheduler. If a task was already flagged overdue and is then marked done, `is_overdue` stays `1` (kept as history). The UI shows "done" styling, not "overdue" styling. |
| Past due dates on create | Allowed (useful for testing). The next scheduler run flags them. |
| Scheduler interval | 2 minutes (set in `config.py`). Also runs once at startup. |
| CSV range filter | Filters on `created_at` by default. Optional `field=due_at`. Dates are inclusive and interpreted as UTC calendar days. |
| Delete / edit title | **Out of scope.** |

---

## 3. Functional Requirements

| ID | Requirement |
|---|---|
| F1 | User can create a task with a title (1 to 200 chars) and a due date/time. |
| F2 | The page lists all tasks ordered by `created_at DESC`, then `due_at ASC`, then `id DESC`. |
| F3 | User can mark a pending task as done. Marking an already-done task is a harmless no-op. |
| F4 | A scheduler runs every 2 minutes. For every task with `status='pending'`, `is_overdue IS NULL`, and `due_at` earlier than now (UTC), it sets `is_overdue=1`, updates `updated_at`, and prints one line per task to the console. |
| F5 | The frontend loads tasks on page load and then re-fetches `GET /api/tasks` every 5 minutes. Overdue tasks are visually different (red). |
| F6 | **(Extra)** User picks a start date and end date, clicks a button, and the browser downloads a CSV of tasks in that range. |

---

## 4. Project Structure

Create exactly this layout:

```
task-manager/
├── app.py
├── config.py
├── db.py
├── scheduler.py
├── utils.py
├── schema.sql
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
└── tests/
    └── test_app.py
```

`requirements.txt`:

```
Flask>=3.0,<4
APScheduler>=3.10,<4
pytest>=8.0
```

> APScheduler **must** stay on v3. Version 4 has a different API and the code below will not work with it.

Setup commands:

```bash
pip install -r requirements.txt
python app.py                    # serves http://127.0.0.1:5000
```

---

## 5. Data Model

### 5.1 `schema.sql`

```sql
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
```

### 5.2 Timestamp format rule

Every timestamp in the DB looks like `2026-10-19T14:30:00Z`. This fixed format sorts and compares correctly as plain text, so SQL can use `<`, `>`, and `ORDER BY` directly on the columns. Never store any other format.

### 5.3 API task object (JSON shape returned by the server)

```json
{
  "id": 1,
  "title": "Create a marketing campaign",
  "created_at": "2026-10-05T09:00:00Z",
  "updated_at": "2026-10-05T09:00:00Z",
  "due_at": "2026-10-19T09:00:00Z",
  "status": "pending",
  "is_overdue": null
}
```

`status` is `"pending"` or `"done"`. `is_overdue` is `true` or `null` (never `false`).

---

## 6. API Specification

All responses are JSON except the HTML page and the CSV export. Errors always look like `{"error": "message"}`.

| Method | Path | Body / Query | Success | Errors |
|---|---|---|---|---|
| GET | `/` | none | 200 HTML page | none |
| GET | `/api/tasks` | none | 200 `[task, ...]` sorted per F2 | none |
| POST | `/api/tasks` | JSON `{"title": str, "due_at": ISO-8601 str}` | 201 `task` | 400 invalid title or `due_at` |
| POST | `/api/tasks/<id>/done` | none | 200 `task` (status `done`) | 404 unknown id |
| GET | `/api/tasks/export` | `start=YYYY-MM-DD` `end=YYYY-MM-DD` `field=created_at\|due_at` (optional, default `created_at`) | 200 `text/csv` attachment | 400 bad or missing params |

### CSV format

- Header row, exactly: `id,title,status,is_overdue,created_at,updated_at,due_at`
- `is_overdue` is written as `true` or `false`.
- Rows ordered by the chosen `field` ascending.
- Filename: `tasks_<start>_to_<end>.csv`.
- Titles starting with `=`, `+`, `-`, or `@` get a leading `'` (prevents spreadsheet formula injection).

### Example calls

```bash
curl -X POST http://127.0.0.1:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Create a marketing campaign","due_at":"2026-10-19T09:00:00Z"}'

curl http://127.0.0.1:5000/api/tasks

curl -X POST http://127.0.0.1:5000/api/tasks/1/done

curl -OJ "http://127.0.0.1:5000/api/tasks/export?start=2026-10-01&end=2026-10-31"
```

---

## 7. Backend Code

### 7.1 `config.py`

```python
import os

DB_PATH = os.environ.get("TASKS_DB_PATH", "tasks.db")
OVERDUE_CHECK_MINUTES = 2
TITLE_MAX_LEN = 200
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
```

### 7.2 `utils.py`

```python
from datetime import datetime, timezone

from config import TIME_FORMAT


def utc_now_str() -> str:
    """Current UTC time in the fixed storage format."""
    return datetime.now(timezone.utc).strftime(TIME_FORMAT)


def normalize_iso(value) -> str:
    """
    Convert an ISO-8601 string (with 'Z' or an offset, or naive = assumed UTC)
    into the fixed UTC storage format. Raises ValueError if invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty or non-string datetime")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(TIME_FORMAT)


def csv_safe(text: str) -> str:
    """Prefix a quote if the text could be run as a spreadsheet formula."""
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text
```

### 7.3 `db.py`

`config.DB_PATH` is read at call time (not imported by name) so tests can swap the DB path.

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config


@contextmanager
def get_conn():
    """Open a new connection, commit on success, rollback on error, always close."""
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema)
```

> Rule: open a **new** connection per request and per scheduler run. Never share one connection between the Flask thread and the scheduler thread.

### 7.4 `scheduler.py`

```python
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from config import OVERDUE_CHECK_MINUTES
from db import get_conn
from utils import utc_now_str


def check_overdue() -> None:
    """Flag pending, unflagged tasks whose due_at has passed, and print them."""
    now = utc_now_str()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, due_at
            FROM tasks
            WHERE status = 'pending'
              AND is_overdue IS NULL
              AND due_at < ?
            """,
            (now,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE tasks SET is_overdue = 1, updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
    for row in rows:
        print(
            f'[OVERDUE] Task #{row["id"]} "{row["title"]}" was due at {row["due_at"]}',
            flush=True,
        )


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        check_overdue,
        trigger="interval",
        minutes=OVERDUE_CHECK_MINUTES,
        id="overdue_check",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),  # also run once right now
    )
    scheduler.start()
    return scheduler
```

### 7.5 `app.py`

```python
import csv
import io
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from config import TITLE_MAX_LEN
from db import get_conn, init_db
from scheduler import start_scheduler
from utils import csv_safe, normalize_iso, utc_now_str

app = Flask(__name__)

EXPORT_FIELDS = ("created_at", "due_at")  # whitelist: safe to place in SQL text


def row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "due_at": row["due_at"],
        "status": row["status"],
        "is_overdue": True if row["is_overdue"] == 1 else None,
    }


def error(message: str, code: int):
    return jsonify({"error": message}), code


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/tasks")
def list_tasks():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC, due_at ASC, id DESC"
        ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.post("/api/tasks")
def create_task():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title or len(title) > TITLE_MAX_LEN:
        return error(f"title must be 1 to {TITLE_MAX_LEN} characters", 400)
    try:
        due_at = normalize_iso(data.get("due_at"))
    except ValueError:
        return error("due_at must be a valid ISO-8601 datetime", 400)

    now = utc_now_str()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, created_at, updated_at, due_at) VALUES (?, ?, ?, ?)",
            (title, now, now, due_at),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/tasks/<int:task_id>/done")
def mark_done(task_id: int):
    now = utc_now_str()
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ? AND status != 'done'",
            (now, task_id),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return error("task not found", 404)
    return jsonify(row_to_dict(row))


@app.get("/api/tasks/export")
def export_csv():
    field = request.args.get("field", "created_at")
    if field not in EXPORT_FIELDS:
        return error("field must be created_at or due_at", 400)
    try:
        start = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
        end = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date()
    except ValueError:
        return error("start and end are required in YYYY-MM-DD format", 400)
    if start > end:
        return error("start must not be after end", 400)

    start_ts = f"{start.isoformat()}T00:00:00Z"
    end_ts = f"{end.isoformat()}T23:59:59Z"

    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE {field} >= ? AND {field} <= ? ORDER BY {field} ASC",
            (start_ts, end_ts),
        ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "status", "is_overdue", "created_at", "updated_at", "due_at"])
    for r in rows:
        writer.writerow([
            r["id"],
            csv_safe(r["title"]),
            r["status"],
            "true" if r["is_overdue"] == 1 else "false",
            r["created_at"],
            r["updated_at"],
            r["due_at"],
        ])

    filename = f"tasks_{start.isoformat()}_to_{end.isoformat()}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    init_db()
    start_scheduler()
    # debug=False is REQUIRED. Debug mode's reloader starts the app twice,
    # which would start two schedulers and print every overdue line twice.
    app.run(host="127.0.0.1", port=5000, debug=False)
```

---

## 8. Frontend Code

### 8.1 `templates/index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task Manager</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <main>
    <h1>Task Manager</h1>

    <section>
      <h2>New task</h2>
      <form id="task-form">
        <input type="text" id="title" maxlength="200" placeholder="e.g. Create a marketing campaign" required>
        <input type="datetime-local" id="due" required>
        <div class="presets">
          <span>Due in:</span>
          <button type="button" data-days="1">+1 day</button>
          <button type="button" data-days="7">+1 week</button>
          <button type="button" data-days="14">+2 weeks</button>
        </div>
        <button type="submit">Add task</button>
      </form>
      <p id="form-error" class="error"></p>
    </section>

    <section>
      <h2>Tasks</h2>
      <p id="last-updated" class="muted"></p>
      <ul id="task-list"></ul>
    </section>

    <section>
      <h2>Export CSV</h2>
      <form id="export-form">
        <label>From <input type="date" id="export-start" required></label>
        <label>To <input type="date" id="export-end" required></label>
        <label>Filter by
          <select id="export-field">
            <option value="created_at">Created date</option>
            <option value="due_at">Due date</option>
          </select>
        </label>
        <button type="submit">Download CSV</button>
      </form>
    </section>
  </main>
  <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
```

### 8.2 `static/app.js`

Never build task HTML with `innerHTML` and user text. Use `textContent` (prevents script injection).

```javascript
const POLL_MS = 5 * 60 * 1000; // 5 minutes
const $ = (id) => document.getElementById(id);

function pad(n) {
  return String(n).padStart(2, "0");
}

// Format a Date for <input type="datetime-local"> (local time, no seconds).
function toLocalInputValue(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
         `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function loadTasks() {
  try {
    const res = await fetch("/api/tasks");
    if (!res.ok) throw new Error("HTTP " + res.status);
    renderTasks(await res.json());
    $("last-updated").textContent = "Last updated: " + new Date().toLocaleTimeString();
  } catch (err) {
    $("last-updated").textContent = "Could not refresh: " + err.message;
  }
}

function renderTasks(tasks) {
  const list = $("task-list");
  list.replaceChildren();

  if (tasks.length === 0) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No tasks yet.";
    list.appendChild(empty);
    return;
  }

  for (const t of tasks) {
    const li = document.createElement("li");
    li.className = "task";
    if (t.status === "done") li.classList.add("done");
    else if (t.is_overdue) li.classList.add("overdue");

    const info = document.createElement("div");

    const title = document.createElement("strong");
    title.textContent = t.title;
    info.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "muted";
    let label = "Due: " + new Date(t.due_at).toLocaleString();
    if (t.status === "done") label += "  ·  DONE";
    else if (t.is_overdue) label += "  ·  OVERDUE";
    meta.textContent = label;
    info.appendChild(meta);

    li.appendChild(info);

    if (t.status === "pending") {
      const btn = document.createElement("button");
      btn.textContent = "Mark done";
      btn.addEventListener("click", () => markDone(t.id));
      li.appendChild(btn);
    }
    list.appendChild(li);
  }
}

async function markDone(id) {
  const res = await fetch(`/api/tasks/${id}/done`, { method: "POST" });
  if (res.ok) loadTasks();
}

$("task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("form-error").textContent = "";
  const body = {
    title: $("title").value,
    // datetime-local is local time; new Date() reads it as local, toISOString() gives UTC.
    due_at: new Date($("due").value).toISOString(),
  };
  const res = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    $("task-form").reset();
    loadTasks();
  } else {
    const data = await res.json().catch(() => ({}));
    $("form-error").textContent = data.error || "Could not create task.";
  }
});

document.querySelectorAll(".presets button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const d = new Date();
    d.setDate(d.getDate() + Number(btn.dataset.days));
    $("due").value = toLocalInputValue(d);
  });
});

$("export-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const params = new URLSearchParams({
    start: $("export-start").value,
    end: $("export-end").value,
    field: $("export-field").value,
  });
  // The server sends Content-Disposition: attachment, so the browser downloads the file.
  window.location.href = "/api/tasks/export?" + params.toString();
});

loadTasks();
setInterval(loadTasks, POLL_MS);
```

### 8.3 `static/style.css`

```css
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; background: #f5f5f7; color: #222; }
main { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
input, select, button { font: inherit; padding: 8px; }
input[type="text"] { flex: 1 1 100%; }
button { cursor: pointer; }
.presets { display: flex; gap: 6px; align-items: center; flex: 1 1 100%; }
.muted { color: #777; font-size: 0.9em; margin: 2px 0; }
.error { color: #b00020; margin: 8px 0 0; }
ul { list-style: none; padding: 0; margin: 0; }
.task { display: flex; justify-content: space-between; align-items: center;
        gap: 12px; padding: 10px; border-left: 4px solid #4caf50;
        background: #fafafa; margin-bottom: 8px; border-radius: 4px; }
.task.overdue { border-left-color: #d32f2f; background: #fdecea; color: #b71c1c; }
.task.done { border-left-color: #9e9e9e; opacity: 0.6; text-decoration: line-through; }
```

---

## 9. Scheduler Behavior (precise)

1. `start_scheduler()` is called once from `app.py`'s `__main__` block.
2. Job `check_overdue` runs immediately, then every `OVERDUE_CHECK_MINUTES` (2) minutes.
3. Each run picks rows matching: `status='pending' AND is_overdue IS NULL AND due_at < <now UTC>`.
4. For each row: set `is_overdue=1`, set `updated_at=<now>`.
5. After the DB commit, print one line per row, exactly:
   `[OVERDUE] Task #<id> "<title>" was due at <due_at>`
6. A task is flagged **once**. Because `is_overdue IS NULL` is in the query, it is never printed again.

---

## 10. Frontend Behavior (precise)

| Event | Behavior |
|---|---|
| Page load | Call `loadTasks()`. |
| Every 5 minutes | `setInterval(loadTasks, 300000)`. |
| Submit new-task form | POST, then reset the form and reload the list. Show the server's error text on failure. |
| Click a preset (+1 day, +1 week, +2 weeks) | Fill the due input with now plus N days in local time. |
| Click "Mark done" | POST to `/api/tasks/<id>/done`, then reload the list. |
| Submit export form | Navigate to `/api/tasks/export?...`; the browser downloads the CSV. |
| Task styling | `done` = grey and struck through. `overdue` (and not done) = red background and "OVERDUE" label. Otherwise = green left border. |

Expected lag: a task can show as overdue up to about 7 minutes after its due time (up to 2 min for the scheduler, plus up to 5 min for the next poll). This is accepted.

---

## 11. Tests: `tests/test_app.py`

Run with `pytest` from the `task-manager/` folder.

```python
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from app import app
from db import init_db
from scheduler import check_overdue


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    return app.test_client()


def iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def titles(client):
    return [t["title"] for t in client.get("/api/tasks").get_json()]


def test_create_and_order(client):
    assert client.post("/api/tasks", json={"title": "A", "due_at": iso(5)}).status_code == 201
    assert client.post("/api/tasks", json={"title": "B", "due_at": iso(1)}).status_code == 201
    # B is newer (or same second but due sooner), so B comes first.
    assert titles(client) == ["B", "A"]


def test_validation(client):
    assert client.post("/api/tasks", json={"title": "  ", "due_at": iso(1)}).status_code == 400
    assert client.post("/api/tasks", json={"title": "X", "due_at": "nope"}).status_code == 400


def test_mark_done(client):
    task = client.post("/api/tasks", json={"title": "A", "due_at": iso(1)}).get_json()
    res = client.post(f"/api/tasks/{task['id']}/done")
    assert res.status_code == 200 and res.get_json()["status"] == "done"
    assert client.post("/api/tasks/9999/done").status_code == 404


def test_overdue_scheduler(client, capsys):
    client.post("/api/tasks", json={"title": "Late", "due_at": iso(-1)})
    client.post("/api/tasks", json={"title": "Later", "due_at": iso(3)})
    check_overdue()
    flags = {t["title"]: t["is_overdue"] for t in client.get("/api/tasks").get_json()}
    assert flags == {"Late": True, "Later": None}
    assert "[OVERDUE]" in capsys.readouterr().out
    check_overdue()  # second run must not print again
    assert capsys.readouterr().out == ""


def test_export_csv(client):
    client.post("/api/tasks", json={"title": "=bad", "due_at": iso(1)})
    res = client.get("/api/tasks/export?start=2000-01-01&end=2100-01-01")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    lines = res.data.decode().splitlines()
    assert lines[0] == "id,title,status,is_overdue,created_at,updated_at,due_at"
    assert "'=bad" in lines[1]
    assert client.get("/api/tasks/export?start=bad&end=2100-01-01").status_code == 400
```

---

## 12. Build Order (with "Done when" checks)

| Step | Do this | Done when |
|---|---|---|
| 1 | Create folders, `requirements.txt`, install deps. | `pip list` shows Flask and APScheduler 3.x. |
| 2 | Create `config.py`, `utils.py`, `schema.sql`, `db.py`. | `python -c "from db import init_db; init_db()"` creates `tasks.db` with no error. |
| 3 | Create `app.py` routes (`/`, list, create, done). Temporarily skip export and scheduler import if needed. | `curl` create then list returns the task. |
| 4 | Create `scheduler.py`; wire into `app.py`. | Creating a task with a past `due_at` prints `[OVERDUE] ...` in the server console within seconds. |
| 5 | Create `index.html`, `app.js`, `style.css`. | Browser at `http://127.0.0.1:5000` can add and complete tasks. |
| 6 | Add the export route and export form. | Clicking "Download CSV" saves a file that opens in a spreadsheet. |
| 7 | Create `tests/test_app.py`. | `pytest` passes all 5 tests. |

---

## 13. Acceptance Criteria (manual checklist)

- [ ] Add "Create a marketing campaign" and click **+2 weeks**; the task appears with a due date about 14 days ahead.
- [ ] Add two tasks; the newest appears at the top of the list.
- [ ] Click **Mark done**; the task turns grey and struck through and the button disappears.
- [ ] Add a task whose due time is in the past. Within about 2 minutes (or immediately at startup), the console prints one `[OVERDUE]` line, and only once for that task.
- [ ] After the next page refresh/poll, that task shows in red with the "OVERDUE" label.
- [ ] Leave the page open for 5 minutes; the "Last updated" time changes without a manual refresh.
- [ ] Export with a wide date range downloads a `.csv` with the exact header from section 6.
- [ ] Export with start after end, or a missing date, shows an error response (HTTP 400), not a crash.
- [ ] Restart the server; all tasks are still there.
- [ ] `pytest` passes.

---

## 14. Common Pitfalls

| Pitfall | Correct approach |
|---|---|
| Scheduler prints twice. | Keep `debug=False` in `app.run(...)`. Never use `flask run --debug` or the reloader. |
| `sqlite3.ProgrammingError` about threads. | Open a new connection per call via `get_conn()`. Never store a global connection. |
| Dates compare wrongly. | Store only `YYYY-MM-DDTHH:MM:SSZ` UTC strings. Always pass user datetimes through `normalize_iso()`. |
| Writing `is_overdue = 0` or `FALSE`. | Never. Only `NULL` or `1`. |
| `ImportError` for APScheduler classes. | You installed v4. Reinstall with `pip install "APScheduler>=3.10,<4"`. |
| Task titles with `<script>` break the page. | Render with `textContent`, never `innerHTML`. |
| Export range misses tasks from the end day. | The end date is expanded to `T23:59:59Z`. Do not compare against `T00:00:00Z`. |

---

## 15. Out of Scope

Authentication, multiple users, editing or deleting tasks, task descriptions or priorities, email/push notifications, natural-language date parsing, pagination, Docker, deployment, and any JavaScript framework or build step.