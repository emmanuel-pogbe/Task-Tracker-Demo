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