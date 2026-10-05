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