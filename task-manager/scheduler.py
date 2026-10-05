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