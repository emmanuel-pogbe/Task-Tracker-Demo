import os

DB_PATH = os.environ.get("TASKS_DB_PATH", "tasks.db")
OVERDUE_CHECK_MINUTES = 2
TITLE_MAX_LEN = 200
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"