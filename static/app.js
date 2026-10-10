/* TrailMate AI frontend. Vanilla JavaScript, no dependencies, no external requests. */
(() => {
  "use strict";

  const STORAGE_ACTIVE = "trailmate.activeMission";
  const ticksKey = (id) => `trailmate.ticks.${id}`;
  const STATUS_LABELS = {
    created: "Not started",
    started: "In progress",
    completed: "Completed (self-reported)",
  };
  const MOOD_LABELS = {
    calm: "Calm", happy: "Happy", energized: "Energized", curious: "Curious",
    grateful: "Grateful", tired: "Tired", neutral: "Neutral",
  };
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = {
    mission: null,
    missions: [],
    checked: new Set(),
    lastFocus: null,
  };
  const timer = { endAt: 0, handle: null };
  let toastHandle = null;

  const $ = (id) => document.getElementById(id);

  /* ------------------------------------------------------------ helpers */

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const store = {
    get(key) { try { return window.localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { window.localStorage.setItem(key, value); } catch { /* storage unavailable */ } },
    remove(key) { try { window.localStorage.removeItem(key); } catch { /* storage unavailable */ } },
  };

  const capitalize = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : "");

  function formatDateTime(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function showError(id, message) { $(id).textContent = message || ""; }

  function toast(message) {
    const node = $("toast");
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toastHandle);
    toastHandle = setTimeout(() => { node.hidden = true; }, 5500);
  }

  function scrollToId(id) {
    $(id).scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }

  async function withBusy(button, task) {
    button.disabled = true;
    try { await task(); } finally { button.disabled = false; }
  }

  function describeError(data, status) {
    const detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      return detail.map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(" › ") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      }).join(" ");
    }
    return `Something went wrong (HTTP ${status}).`;
  }

  async function api(path, options = {}) {
    const init = {
      ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
    };
    let response;
    try {
      response = await fetch(path, init);
    } catch {
      throw new Error("Could not reach the TrailMate server. Make sure it is still running in your terminal.");
    }
    if (response.status === 204) return null;
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) throw new Error(describeError(data, response.status));
    return data;
  }

  /* ------------------------------------------------------------ health */

  async function loadHealth() {
    const pill = $("health-pill");
    const text = $("health-text");
    try {
      const health = await api("/api/health");
      if (health.ollama_available && health.model_ready) {
        pill.dataset.state = "ready";
        text.textContent = `Local AI ready · ${health.model}`;
      } else if (health.ollama_available) {
        pill.dataset.state = "warn";
        text.textContent = `Model not installed · run: ollama pull ${health.model}`;
      } else {
        pill.dataset.state = "off";
        text.textContent = "Ollama not detected · built-in missions will be used";
      }
    } catch {
      pill.dataset.state = "off";
      text.textContent = "Server unreachable";
    }
  }

  /* ------------------------------------------------------------ stats and recent activity */

  async function loadStats() {
    try {
      const stats = await api("/api/stats");
      $("stat-created").textContent = stats.missions_created;
      $("stat-completed").textContent = stats.missions_completed;
      $("stat-minutes").textContent = stats.self_reported_outdoor_minutes;
      $("stat-journal").textContent = stats.journal_entries;
      $("stats-note").textContent =
        `${stats.verification_note} Outdoor minutes add up the planned length of missions you marked complete. ` +
        `Independently verified minutes: ${stats.verified_outdoor_minutes}.`;
      renderRecent(stats.recent_activity);
    } catch (error) {
      $("stats-note").textContent = `Could not load progress: ${error.message}`;
    }
  }

  function renderRecent(items) {
    const list = $("recent-list");
    list.replaceChildren();
    $("recent-empty").hidden = items.length > 0;
    items.forEach((mission) => {
      const meta = [
        STATUS_LABELS[mission.status] || mission.status,
        `${mission.duration_minutes} min`,
        formatDateTime(mission.created_at),
        mission.source === "ai" ? "AI-written" : "Built-in template",
      ].join(" · ");
      list.append(el("li", { class: "recent-item" },
        el("div", { class: "recent-main" },
          el("p", { class: "recent-title", text: mission.title }),
          el("p", { class: "recent-meta", text: meta })),
        el("button", {
          class: "btn btn-ghost btn-small", type: "button",
          "aria-label": `Open mission ${mission.title}`,
          onclick: () => { openMission(mission); scrollToId("mission"); },
        }, "Open")));
    });
  }

  /* ------------------------------------------------------------ missions list */

  async function loadMissions() {
    try {
      state.missions = await api("/api/missions?limit=20");
      populateJournalMissions(state.mission ? state.mission.id : null);
    } catch (error) {
      toast(`Could not load missions: ${error.message}`);
    }
  }

  function restoreActiveMission() {
    const storedId = Number(store.get(STORAGE_ACTIVE));
    const mission =
      state.missions.find((item) => item.id === storedId) ||
      state.missions.find((item) => item.status !== "completed") ||
      null;
    if (mission) openMission(mission);
    else renderMission();
  }

  /* ------------------------------------------------------------ generate a mission */

  function onEnvironmentChange() {
    const other = $("environment-select").value === "other";
    $("environment-other-wrap").hidden = !other;
    $("environment-other").required = other;
  }

  function readForm() {
    const form = $("mission-form");
    const duration = Number((form.querySelector('input[name="duration"]:checked') || {}).value);
    const difficulty = (form.querySelector('input[name="difficulty"]:checked') || {}).value;
    const interests = Array.from(form.querySelectorAll('input[name="interest"]:checked'), (box) => box.value);
    const selected = $("environment-select").value;
    const environment = selected === "other"
      ? $("environment-other").value.trim().replace(/\s+/g, " ")
      : selected;

    if (!duration || !difficulty) return { error: "Choose how much time you have and how adventurous you feel." };
    if (interests.length === 0) return { error: "Pick at least one interest." };
    if (!environment) return { error: "Describe the place you will be in." };
    if (environment.length > 120) return { error: "Keep the place description under 120 characters." };
    return { payload: { duration_minutes: duration, interests, environment, difficulty } };
  }

  function setGenerating(on) {
    const button = $("generate-btn");
    button.disabled = on;
    button.setAttribute("aria-busy", String(on));
    $("generate-spinner").hidden = !on;
    $("generate-label").textContent = on ? "Writing your mission…" : "Create my mission";
    $("form-status").textContent = on
      ? "Asking the local model. The first request can take up to a minute while it loads. If it can't answer, a built-in mission is used instead."
      : "";
  }

  async function onGenerate(event) {
    event.preventDefault();
    showError("form-error", "");
    const result = readForm();
    if (result.error) {
      showError("form-error", result.error);
      return;
    }
    setGenerating(true);
    try {
      const mission = await api("/api/missions", { method: "POST", body: JSON.stringify(result.payload) });
      openMission(mission);
      toast(mission.source === "ai"
        ? `Mission written by ${mission.model_name} on your device.`
        : "Local AI wasn't available, so a built-in mission template was used.");
      await Promise.all([loadMissions(), loadStats(), loadHealth()]);
      scrollToId("mission");
      $("mission-title").focus({ preventScroll: true });
    } catch (error) {
      showError("form-error", error.message);
    } finally {
      setGenerating(false);
    }
  }

  /* ------------------------------------------------------------ mission view */

  function loadTicks(mission) {
    try {
      const parsed = JSON.parse(store.get(ticksKey(mission.id)) || "[]");
      if (!Array.isArray(parsed)) return new Set();
      return new Set(parsed.filter((n) => Number.isInteger(n) && n >= 0 && n < mission.tasks.length));
    } catch {
      return new Set();
    }
  }

  function saveTicks() {
    if (state.mission) store.set(ticksKey(state.mission.id), JSON.stringify([...state.checked]));
  }

  function openMission(mission) {
    stopTimer();
    state.mission = mission;
    state.checked = loadTicks(mission);
    store.set(STORAGE_ACTIVE, String(mission.id));
    $("timer-enabled").checked = false;
    $("timer-controls").hidden = true;
    $("timer-note").textContent = "";
    $("timer-minutes").value = mission.duration_minutes;
    showError("mission-error", "");
    renderMission();
    populateJournalMissions(mission.id);
  }

  function applyUpdate(mission) {
    state.mission = mission;
    state.missions = state.missions.map((item) => (item.id === mission.id ? mission : item));
    renderMission();
  }

  function renderMission() {
    const mission = state.mission;
    $("mission-empty").hidden = Boolean(mission);
    $("mission-view").hidden = !mission;
    if (!mission) return;

    $("mission-title").textContent = mission.title;
    $("mission-description").textContent = mission.description;
    $("mission-focus").textContent = `Focus: ${mission.interests.map(capitalize).join(", ")}`;
    $("mission-reminder").textContent = mission.phone_reminder;
    $("mission-source-note").textContent = mission.source === "ai"
      ? "Written locally by Gemma through Ollama. It has no access to live weather, maps or wildlife data, so check conditions yourself and stay somewhere safe and public."
      : "The local model wasn't available (or didn't return a usable mission), so TrailMate used one of its hand-written templates. This mission was not written by AI.";
    renderBadges(mission);
    renderTasks(mission);
    renderProgress();
    renderEncouragement();
    renderControls();
  }

  function renderBadges(mission) {
    const box = $("mission-badges");
    box.replaceChildren(
      mission.source === "ai"
        ? el("span", { class: "badge badge-ai", text: `AI-written by ${mission.model_name || "local model"} on your device` })
        : el("span", { class: "badge badge-fallback", text: "Built-in template · not AI-generated" }),
      el("span", { class: "badge", text: `${mission.duration_minutes} min` }),
      el("span", { class: "badge", text: capitalize(mission.difficulty) }),
      el("span", { class: "badge", text: mission.environment }),
      el("span", { class: `badge status-${mission.status}`, text: STATUS_LABELS[mission.status] || mission.status }),
    );
  }

  function renderTasks(mission) {
    const list = $("task-list");
    list.replaceChildren();
    mission.tasks.forEach((task, index) => {
      if (mission.status === "completed") {
        list.append(el("li", { class: "task-static" }, el("span", { class: "task-text", text: task })));
        return;
      }
      const id = `task-${index}`;
      const checked = state.checked.has(index);
      const input = el("input", {
        type: "checkbox", id, checked, disabled: mission.status === "created",
        onchange: (event) => onTaskToggle(index, event.target),
      });
      list.append(el("li", { class: checked ? "task is-done" : "task" },
        el("label", { for: id },
          input,
          el("span", { class: "task-box", "aria-hidden": "true" }),
          el("span", { class: "task-text", text: task }))));
    });
  }

  function onTaskToggle(index, input) {
    if (input.checked) state.checked.add(index);
    else state.checked.delete(index);
    saveTicks();
    input.closest("li").classList.toggle("is-done", input.checked);
    showError("mission-error", "");
    renderProgress();
    renderEncouragement();
  }

  function progressNumbers() {
    const total = state.mission.tasks.length;
    const done = state.mission.status === "completed" ? state.mission.completed_task_count : state.checked.size;
    return { done, total };
  }

  function renderProgress() {
    const { done, total } = progressNumbers();
    const percent = total ? Math.round((done / total) * 100) : 0;
    $("progress-fill").style.width = `${percent}%`;
    const track = $("progress-track");
    track.setAttribute("aria-valuenow", String(percent));
    track.setAttribute("aria-valuetext", `${done} of ${total} tasks`);
    $("progress-label").textContent = state.mission.status === "completed"
      ? `You reported ${done} of ${total} tasks`
      : `${done} of ${total} tasks`;
  }

  function renderEncouragement() {
    const { done, total } = progressNumbers();
    const mission = state.mission;
    let message;
    if (mission.status === "completed") message = "Mission complete. You chose the outdoors over the screen.";
    else if (mission.status === "created") message = "Ready when you are. Press Start, then lock your phone and head out.";
    else if (done === 0) message = "You've started. Look up, take a breath, and begin with the first task.";
    else if (done === total) message = "Every task ticked! Take one last slow look around before you head back.";
    else if (done / total >= 0.5) message = "More than halfway. Keep your eyes up and enjoy it.";
    else message = "Nice start. One small thing at a time.";
    $("encouragement").textContent = message;
  }

  function renderControls() {
    const status = state.mission.status;
    $("start-btn").hidden = status !== "created";
    $("outside-btn").hidden = status !== "started";
    $("complete-btn").hidden = status !== "started";
    $("timer-panel").hidden = status !== "started";
    $("complete-panel").hidden = status !== "completed";
    $("mission-actions").hidden = status === "completed";
  }

  async function onStart() {
    const mission = state.mission;
    if (!mission) return;
    await withBusy($("start-btn"), async () => {
      try {
        const updated = await api(`/api/missions/${mission.id}/start`, { method: "PATCH" });
        applyUpdate(updated);
        toast("Mission started. Lock your phone when you head out.");
        await loadStats();
      } catch (error) {
        showError("mission-error", error.message);
      }
    });
  }

  async function onComplete() {
    const mission = state.mission;
    if (!mission) return;
    const count = state.checked.size;
    if (count < 1) {
      showError("mission-error", "Tick at least one task you really did before marking the mission complete. Only honest progress counts.");
      return;
    }
    await withBusy($("complete-btn"), async () => {
      try {
        const updated = await api(`/api/missions/${mission.id}/complete`, {
          method: "PATCH",
          body: JSON.stringify({ completed_task_count: count }),
        });
        stopTimer();
        closeOverlay();
        store.remove(ticksKey(updated.id));
        applyUpdate(updated);
        showError("mission-error", "");
        toast("Mission complete. Nicely done.");
        populateJournalMissions(updated.id);
        await Promise.all([loadMissions(), loadStats()]);
        $("complete-heading").focus();
      } catch (error) {
        showError("mission-error", error.message);
      }
    });
  }

  /* ------------------------------------------------------------ optional timer */

  function formatClock(ms) {
    const seconds = Math.max(0, Math.ceil(ms / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function setTimerDisplays(text) {
    $("timer-display").textContent = text;
    $("overlay-timer").textContent = text;
  }

  function stopTimer() {
    if (timer.handle !== null) {
      clearInterval(timer.handle);
      timer.handle = null;
    }
    $("timer-toggle").textContent = "Start timer";
    $("timer-minutes").disabled = false;
    $("overlay-timer").hidden = true;
    setTimerDisplays("0:00");
  }

  function startTimer() {
    const minutes = Math.round(Number($("timer-minutes").value));
    if (!Number.isFinite(minutes) || minutes < 1 || minutes > 180) {
      $("timer-note").textContent = "Enter a timer length between 1 and 180 minutes.";
      return;
    }
    $("timer-note").textContent = "";
    timer.endAt = Date.now() + minutes * 60000;
    $("timer-toggle").textContent = "Stop timer";
    $("timer-minutes").disabled = true;
    $("overlay-timer").hidden = false;
    timer.handle = setInterval(tickTimer, 250);
    tickTimer();
  }

  function tickTimer() {
    const remaining = timer.endAt - Date.now();
    if (remaining > 0) {
      setTimerDisplays(formatClock(remaining));
      return;
    }
    stopTimer();
    $("timer-note").textContent =
      "Time's up. Stay out longer if you like. TrailMate will not mark the mission complete for you. Do that yourself once you've done the tasks.";
    if (!$("outside-overlay").hidden) {
      $("overlay-timer").hidden = false;
      $("overlay-timer").textContent = "Time's up";
    }
    toast("Timer finished. Your mission is still waiting for you to say you're done.");
  }

  function onTimerToggle() {
    if (timer.handle !== null) stopTimer();
    else startTimer();
  }

  function onTimerEnabledChange() {
    const enabled = $("timer-enabled").checked;
    $("timer-controls").hidden = !enabled;
    if (!enabled) {
      stopTimer();
      $("timer-note").textContent = "";
    }
  }

  /* ------------------------------------------------------------ "go outside" screen */

  function openOverlay() {
    if (!state.mission) return;
    $("overlay-mission").textContent = state.mission.title;
    $("overlay-task-list").replaceChildren(...state.mission.tasks.map((task) => el("li", { text: task })));
    $("overlay-timer").hidden = timer.handle === null;
    state.lastFocus = document.activeElement;
    $("outside-overlay").hidden = false;
    document.body.classList.add("no-scroll");
    $("overlay-close").focus();
  }

  function closeOverlay() {
    if ($("outside-overlay").hidden) return;
    $("outside-overlay").hidden = true;
    document.body.classList.remove("no-scroll");
    if (state.lastFocus && typeof state.lastFocus.focus === "function") state.lastFocus.focus();
  }

  /* ------------------------------------------------------------ journal */

  function populateJournalMissions(preferredId) {
    const select = $("journal-mission");
    const previous = preferredId || (select.value ? Number(select.value) : null);
    select.replaceChildren(el("option", { value: "", text: "Not linked to a mission" }));
    state.missions.forEach((mission) => {
      select.append(el("option", {
        value: String(mission.id),
        text: `${mission.title} · ${formatDateTime(mission.created_at)}`,
      }));
    });
    if (previous && state.missions.some((mission) => mission.id === previous)) {
      select.value = String(previous);
    }
  }

  async function loadJournal() {
    try {
      renderJournal(await api("/api/journal?limit=100"));
    } catch (error) {
      showError("journal-error", `Could not load your journal: ${error.message}`);
    }
  }

  function renderJournal(entries) {
    const list = $("journal-list");
    list.replaceChildren();
    $("journal-empty").hidden = entries.length > 0;
    entries.forEach((entry) => {
      const stamp = formatDateTime(entry.created_at);
      list.append(el("article", { class: "entry" },
        el("header", { class: "entry-head" },
          el("span", { class: `mood mood-${entry.mood}`, text: MOOD_LABELS[entry.mood] || entry.mood }),
          el("time", { datetime: entry.created_at, text: stamp })),
        el("p", { class: "entry-text", text: entry.content }),
        el("footer", { class: "entry-foot" },
          entry.mission_title
            ? el("span", { class: "entry-mission", text: `Mission: ${entry.mission_title}` })
            : el("span", { class: "entry-mission muted", text: "Free note" }),
          el("button", {
            class: "btn btn-ghost btn-small", type: "button",
            "aria-label": `Delete journal entry from ${stamp}`,
            onclick: () => onDeleteEntry(entry.id),
          }, "Delete"))));
    });
  }

  function updateCount() {
    $("journal-count").textContent = `${$("journal-content").value.length} / 2000`;
  }

  async function onJournalSubmit(event) {
    event.preventDefault();
    showError("journal-error", "");
    const content = $("journal-content").value.trim();
    if (!content) {
      showError("journal-error", "Write a few words about what you saw, heard or felt first.");
      $("journal-content").focus();
      return;
    }
    const body = { content, mood: $("journal-mood").value };
    const missionValue = $("journal-mission").value;
    if (missionValue) body.mission_id = Number(missionValue);

    await withBusy($("journal-submit"), async () => {
      try {
        await api("/api/journal", { method: "POST", body: JSON.stringify(body) });
        $("journal-content").value = "";
        updateCount();
        toast("Saved to your local journal.");
        await Promise.all([loadJournal(), loadStats()]);
      } catch (error) {
        showError("journal-error", error.message);
      }
    });
  }

  async function onDeleteEntry(entryId) {
    if (!window.confirm("Delete this journal entry? This can't be undone.")) return;
    try {
      await api(`/api/journal/${entryId}`, { method: "DELETE" });
      toast("Entry deleted.");
      await Promise.all([loadJournal(), loadStats()]);
    } catch (error) {
      showError("journal-error", error.message);
    }
  }

  function onWriteJournal() {
    if (state.mission) populateJournalMissions(state.mission.id);
    scrollToId("journal");
    $("journal-content").focus({ preventScroll: true });
  }

  /* ------------------------------------------------------------ startup */

  function wireEvents() {
    $("mission-form").addEventListener("submit", onGenerate);
    $("environment-select").addEventListener("change", onEnvironmentChange);
    $("start-btn").addEventListener("click", onStart);
    $("complete-btn").addEventListener("click", onComplete);
    $("outside-btn").addEventListener("click", openOverlay);
    $("overlay-close").addEventListener("click", closeOverlay);
    $("timer-enabled").addEventListener("change", onTimerEnabledChange);
    $("timer-toggle").addEventListener("click", onTimerToggle);
    $("journal-form").addEventListener("submit", onJournalSubmit);
    $("journal-content").addEventListener("input", updateCount);
    $("write-journal-btn").addEventListener("click", onWriteJournal);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeOverlay();
    });
  }

  async function init() {
    wireEvents();
    onEnvironmentChange();
    updateCount();
    await Promise.all([
      loadHealth(),
      loadMissions().then(restoreActiveMission),
      loadStats(),
      loadJournal(),
    ]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();