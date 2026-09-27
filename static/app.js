/* CPRT console: background-task banner, sortable tables, quick filters. No libraries. */
(function () {
  "use strict";
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const banner = $("#job");
  const state = window.CPRT || {};
  let timer = null;

  function watching() { return sessionStorage.getItem("cprt-watching"); }

  function render(job) {
    if (!banner) return;
    if (!job || !job.id) { banner.hidden = true; return; }
    const running = job.status === "running";
    const updated = Date.parse(job.updated || job.started || 0);
    const recent = running || Date.now() - updated < 20 * 60 * 1000;
    if (!recent || (!running && localStorage.getItem("cprt-dismissed") === job.id)) { banner.hidden = true; return; }
    banner.hidden = false;
    banner.className = "job " + (job.status || "");
    const title = running ? job.label : job.status === "done" ? job.label + " finished" : job.label + " didn't finish";
    $(".job-title", banner).textContent = title;
    $(".job-msg", banner).textContent = job.message || "";
    $(".job-log", banner).textContent = (job.log_tail || []).join("\n");
    $(".progress", banner).hidden = !running;
    $(".job-stop", banner).hidden = !(running && (job.kind === "capture_guided" || job.kind === "scan_guided"));
    $(".job-stop", banner).dataset.id = job.id;
    $(".job-close", banner).hidden = running;
    $(".job-close", banner).dataset.id = job.id;
  }

  async function poll() {
    clearTimeout(timer);
    try {
      const res = await fetch("/api/job", { cache: "no-store" });
      const job = await res.json();
      render(job);
      if (job.status === "running") {
        timer = setTimeout(poll, 1500);
      } else if (job.id && watching() === job.id) {
        sessionStorage.removeItem("cprt-watching");
        if (job.status === "done") setTimeout(() => location.reload(), 900);
      }
    } catch (err) {
      timer = setTimeout(poll, 4000);
    }
  }

  function flash(message, kind) {
    const el = document.createElement("div");
    el.className = "flash " + (kind || "error");
    el.setAttribute("role", "alert");
    el.textContent = message;
    const main = $(".main");
    main.insertBefore(el, banner ? banner.nextSibling : main.firstChild);
    setTimeout(() => el.remove(), 9000);
  }

  async function start(kind, body) {
    try {
      const res = await fetch("/api/jobs/" + kind, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify(body || {}),
      });
      const data = await res.json();
      if (!res.ok) { flash(data.error || "That task couldn't start."); return; }
      sessionStorage.setItem("cprt-watching", data.id);
      localStorage.removeItem("cprt-dismissed");
      render(data);
      poll();
    } catch (err) {
      flash("The console isn't responding. Check that its Terminal window is still open.");
    }
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-job]");
    if (trigger) {
      e.preventDefault();
      if (trigger.dataset.confirm && !confirm(trigger.dataset.confirm)) return;
      start(trigger.dataset.job, trigger.dataset.platform ? { platform: trigger.dataset.platform } : {});
      return;
    }
    const stop = e.target.closest(".job-stop");
    if (stop) {
      fetch("/api/job/" + stop.dataset.id + "/stop", { method: "POST", headers: { "X-Requested-With": "fetch" } });
      $(".job-msg", banner).textContent = "Stopping and saving what was recorded...";
      return;
    }
    const close = e.target.closest(".job-close");
    if (close) { localStorage.setItem("cprt-dismissed", close.dataset.id); banner.hidden = true; }
  });

  // Confirm before destructive form submits.
  document.addEventListener("submit", (e) => {
    const msg = e.target.dataset.confirm;
    if (msg && !confirm(msg)) e.preventDefault();
  });

  // Sortable tables: click a column heading.
  $$("table.sortable").forEach((table) => {
    $$("thead th", table).forEach((th, index) => {
      th.tabIndex = 0;
      const sort = () => {
        const body = table.tBodies[0];
        const dir = th.dataset.dir === "desc" ? "asc" : "desc";
        $$("thead th", table).forEach((x) => delete x.dataset.dir);
        th.dataset.dir = dir;
        const value = (row) => {
          const cell = row.cells[index];
          const raw = cell ? (cell.dataset.sort !== undefined ? cell.dataset.sort : cell.textContent.trim()) : "";
          const n = parseFloat(raw.replace(/[,%$+]/g, "").replace("\u2013", ""));
          return isNaN(n) ? raw.toLowerCase() : n;
        };
        Array.from(body.rows)
          .sort((a, b) => {
            const x = value(a), y = value(b);
            if (typeof x !== typeof y) return typeof x === "number" ? -1 : 1;
            return (x > y ? 1 : x < y ? -1 : 0) * (dir === "asc" ? 1 : -1);
          })
          .forEach((row) => body.appendChild(row));
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", (ev) => { if (ev.key === "Enter") sort(); });
    });
  });

  // Instant text filter: <input data-filter="#table-id">
  $$("input[data-filter]").forEach((input) => {
    const table = $(input.dataset.filter);
    if (!table) return;
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      $$("tbody tr", table).forEach((row) => { row.hidden = q && !row.textContent.toLowerCase().includes(q); });
    });
  });

  // Auto-submit selects marked data-autosubmit.
  $$("select[data-autosubmit]").forEach((sel) => sel.addEventListener("change", () => sel.form.submit()));

  render(state.job);
  if (state.job && state.job.status === "running") poll();
  else if (state.job && watching() === state.job.id) sessionStorage.removeItem("cprt-watching");
})();
