/* Medication Tracker sidebar panel. Plain web component, no build step. */
(() => {
  if (customElements.get("medication-tracker-panel")) return;

  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const STATUS_CLASS = {
    Taken: "ok",
    "Due Now": "warn",
    Snoozed: "warn",
    "Missed Dose": "bad",
    Skipped: "muted",
    "On Track": "muted",
  };
  const STATUS_LABEL = { "On Track": "Upcoming", "Due Now": "Due now", "Missed Dose": "Missed" };
  const POLL_MS = 30000;

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fmtDateTime = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };

  const blankForm = (profiles) => ({
    medication_id: null,
    profile_name: Object.values(profiles || {}).length === 1 ? Object.values(profiles)[0] : "",
    medication_name: "",
    dosage: "1 tablet",
    schedules: ["08:00"],
    days: [0, 1, 2, 3, 4, 5, 6],
    quantity: "",
    refill_at: "",
    notes: "",
    instructions: "",
    purpose: "",
    form: "",
    nfc_tag_id: "",
    notification_enabled: true,
    notify_service: "",
    repeat_every_minutes: 5,
    max_repeats: 2,
    reminder_minutes: 15,
    missed_after_minutes: 60,
    duplicate_guard_minutes: 0,
    caregiver_name: "",
    caregiver_notify_service: "",
    confirmation_required: false,
    database_entry_id: null,
  });

  const formFromSnapshot = (s) => ({
    medication_id: s.medication_id,
    profile_name: s.profile_name,
    medication_name: s.medication_name,
    dosage: s.dosage,
    schedules: [...(s.schedules || [])],
    days: s.days_of_week && s.days_of_week.length ? [...s.days_of_week] : [0, 1, 2, 3, 4, 5, 6],
    quantity: s.remaining_quantity ?? "",
    refill_at: s.refill_at ?? "",
    notes: s.notes || "",
    instructions: s.instructions || "",
    purpose: s.purpose || "",
    form: s.form || "",
    nfc_tag_id: s.nfc_tag_id || "",
    notification_enabled: s.notification_enabled !== false,
    notify_service: s.notify_service || "",
    repeat_every_minutes: s.repeat_every_minutes ?? 5,
    max_repeats: s.max_repeats ?? 2,
    reminder_minutes: s.reminder_minutes ?? 15,
    missed_after_minutes: s.missed_after_minutes ?? 60,
    duplicate_guard_minutes: s.duplicate_guard_minutes ?? 0,
    caregiver_name: s.caregiver_name || "",
    caregiver_notify_service: s.caregiver_notify_service || "",
    confirmation_required: !!s.confirmation_required,
    database_entry_id: s.database_entry_id || null,
  });

  const num = (value) => (value === "" || value === null || value === undefined ? null : Number(value));

  const STYLE = `
    :host { display:block; background:var(--primary-background-color); color:var(--primary-text-color); min-height:100%; font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
    * { box-sizing:border-box; }
    .bar { display:flex; align-items:center; gap:8px; padding:12px 16px; background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff); position:sticky; top:0; z-index:5; }
    .bar h1 { font-size:20px; font-weight:500; margin:0; flex:1; }
    .menu { background:none; border:0; color:inherit; font-size:24px; cursor:pointer; padding:4px 8px; }
    .tabs { display:flex; gap:4px; padding:0 8px; background:var(--app-header-background-color, var(--primary-color)); overflow-x:auto; }
    .tab { background:none; border:0; color:inherit; opacity:.75; padding:12px 14px; cursor:pointer; font-size:14px; border-bottom:3px solid transparent; color:var(--app-header-text-color,#fff); white-space:nowrap; }
    .tab.active { opacity:1; border-bottom-color:currentColor; }
    main { max-width:900px; margin:0 auto; padding:16px; }
    .card { background:var(--card-background-color, #fff); border-radius:var(--ha-card-border-radius, 12px); box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.2)); padding:16px; margin-bottom:16px; }
    .card h2 { margin:0 0 12px; font-size:16px; font-weight:500; }
    .row { display:flex; align-items:center; gap:12px; padding:10px 0; border-top:1px solid var(--divider-color); flex-wrap:wrap; }
    .row:first-of-type { border-top:0; }
    .time { font-variant-numeric:tabular-nums; font-weight:600; min-width:52px; }
    .grow { flex:1; min-width:140px; }
    .sub { color:var(--secondary-text-color); font-size:13px; }
    .chip { font-size:12px; padding:3px 10px; border-radius:12px; white-space:nowrap; }
    .chip.ok { background:rgba(67,160,71,.18); color:#2e7d32; }
    .chip.warn { background:rgba(255,160,0,.2); color:#b26a00; }
    .chip.bad { background:rgba(229,57,53,.18); color:#c62828; }
    .chip.muted { background:var(--divider-color); color:var(--secondary-text-color); }
    button.btn { font:inherit; font-size:14px; border:0; border-radius:18px; padding:8px 16px; cursor:pointer; background:var(--primary-color); color:var(--text-primary-color, #fff); }
    button.btn.secondary { background:transparent; color:var(--primary-color); border:1px solid var(--divider-color); }
    button.btn.danger { background:transparent; color:var(--error-color, #c62828); border:1px solid var(--divider-color); }
    button.btn.big { padding:12px 24px; font-size:16px; }
    button.btn[disabled] { opacity:.5; cursor:default; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; }
    .hero { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
    .banner { padding:10px 14px; border-radius:8px; margin-bottom:12px; background:rgba(255,160,0,.18); }
    .empty { text-align:center; padding:32px 8px; color:var(--secondary-text-color); }
    label.field { display:flex; flex-direction:column; gap:4px; font-size:13px; color:var(--secondary-text-color); }
    input, select, textarea { font:inherit; padding:8px 10px; border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); min-width:0; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; }
    .days { display:flex; gap:6px; flex-wrap:wrap; }
    .days label { cursor:pointer; padding:6px 10px; border:1px solid var(--divider-color); border-radius:16px; font-size:13px; color:var(--primary-text-color); user-select:none; }
    .days input { display:none; }
    .days input:checked + span { font-weight:600; color:var(--primary-color); }
    .days label:has(input:checked) { border-color:var(--primary-color); background:rgba(3,169,244,.12); }
    .times { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#323232; color:#fff; padding:10px 18px; border-radius:8px; z-index:20; max-width:90vw; }
    .toast.err { background:#b71c1c; }
    details { margin-top:12px; } summary { cursor:pointer; color:var(--primary-color); }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th, td { text-align:left; padding:8px 6px; border-top:1px solid var(--divider-color); }
    th { font-weight:500; color:var(--secondary-text-color); border-top:0; }
    @media (max-width:600px) { main { padding:8px; } .hide-narrow { display:none; } }
  `;

  class MedicationTrackerPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._state = null;
      this._tab = "today";
      this._form = null;
      this._settingsDraft = null;
      this._toast = null;
      this._scan = null;
      this._busy = false;
      this._timer = null;
      this._narrow = false;
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
      this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("change", (e) => this._onInput(e));
    }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) {
        this._load();
      }
    }
    get hass() {
      return this._hass;
    }
    set narrow(value) {
      this._narrow = !!value;
    }
    set panel(_value) {}
    set route(_value) {}

    connectedCallback() {
      this._render();
      if (!this._timer) this._timer = setInterval(() => this._poll(), POLL_MS);
    }
    disconnectedCallback() {
      clearInterval(this._timer);
      this._timer = null;
      this._stopScan();
    }

    get _isAdmin() {
      return !!(this._hass && this._hass.user && this._hass.user.is_admin);
    }

    async _call(msg) {
      return this._hass.callWS(msg);
    }

    async _load() {
      try {
        this._state = await this._call({ type: "medication_tracker/get_state" });
        this._loadError = null;
      } catch (err) {
        this._loadError = err && err.message ? err.message : "Could not load Medication Tracker";
      }
      this._render();
    }

    _poll() {
      // Never refresh underneath a form the user is typing in.
      if (this._form || this._tab === "settings") return;
      this._load();
    }

    _say(message, error = false) {
      this._toast = { message, error };
      this._render();
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this._toast = null;
        this._render();
      }, 4000);
    }

    async _run(msg, okText) {
      if (this._busy) return null;
      this._busy = true;
      try {
        const result = await this._call(msg);
        if (okText) this._say(okText);
        await this._load();
        return result;
      } catch (err) {
        this._say((err && err.message) || "Something went wrong", true);
        return null;
      } finally {
        this._busy = false;
      }
    }

    // ---------------------------------------------------------------- events

    _onClick(event) {
      const target = event.target.closest("[data-action]");
      if (!target) return;
      const { action, id, profile, minutes, index, tab } = target.dataset;
      switch (action) {
        case "menu":
          this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
          break;
        case "tab":
          this._stopScan();
          this._tab = tab;
          this._form = null;
          if (tab === "settings") this._settingsDraft = JSON.parse(JSON.stringify(this._state.settings));
          this._render();
          break;
        case "take":
          this._run({ type: "medication_tracker/take", medication_id: id }, "Marked as taken");
          break;
        case "take-all":
          this._run(
            { type: "medication_tracker/take_all", ...(profile ? { profile_id: profile } : {}) },
            "Marked everything due as taken"
          );
          break;
        case "skip":
          this._run({ type: "medication_tracker/skip", medication_id: id }, "Skipped");
          break;
        case "snooze":
          this._run({ type: "medication_tracker/snooze", medication_id: id, minutes: Number(minutes || 10) }, "Snoozed");
          break;
        case "add":
          this._form = blankForm(this._state.profiles);
          this._tab = "medications";
          this._render();
          break;
        case "edit": {
          const snap = this._state.medications.find((m) => m.medication_id === id);
          if (snap) {
            this._form = formFromSnapshot(snap);
            this._render();
          }
          break;
        }
        case "cancel":
          this._stopScan();
          this._form = null;
          this._render();
          break;
        case "save":
          this._saveForm();
          break;
        case "delete": {
          const snap = this._state.medications.find((m) => m.medication_id === id);
          if (snap && window.confirm(`Delete ${snap.medication_name} for ${snap.profile_name}, including its history?`)) {
            this._run({ type: "medication_tracker/delete_medication", medication_id: id }, "Deleted");
          }
          break;
        }
        case "refill": {
          const answer = window.prompt("How many doses did you add to the stock?", "30");
          const qty = Number(answer);
          if (answer && qty > 0) {
            this._run({ type: "medication_tracker/refill", medication_id: id, quantity: qty }, "Stock updated");
          }
          break;
        }
        case "reset-history":
          if (window.confirm("Forget missed doses so far and start counting from now?")) {
            this._run({ type: "medication_tracker/reset_history", medication_id: id }, "History reset");
          }
          break;
        case "test": {
          this._call({ type: "medication_tracker/test_notification", medication_id: id, alert_type: "due" })
            .then((r) => this._say(r.delivered ? "Test notification sent to your phone" : "Could not reach the phone. Check the notify service in Settings.", !r.delivered))
            .catch((err) => this._say(err.message, true));
          break;
        }
        case "delete-dose":
          if (window.confirm("Delete this logged dose?")) {
            this._run(
              { type: "medication_tracker/delete_dose", medication_id: id, taken_at: target.dataset.takenAt },
              "Dose deleted"
            );
          }
          break;
        case "add-time":
          this._form.schedules.push("12:00");
          this._render();
          break;
        case "remove-time":
          if (this._form.schedules.length > 1) {
            this._form.schedules.splice(Number(index), 1);
            this._render();
          }
          break;
        case "scan-form":
          this._startScan((tag) => {
            this._form.nfc_tag_id = tag;
            this._render();
          });
          break;
        case "scan-all":
          this._startScan((tag) => {
            const list = new Set(this._settingsDraft.all_tag_ids || []);
            list.add(tag);
            this._settingsDraft.all_tag_ids = [...list];
            this._render();
          });
          break;
        case "scan-profile":
          this._startScan((tag) => {
            const map = { ...(this._settingsDraft.profile_tags || {}) };
            for (const key of Object.keys(map)) if (map[key] === profile) delete map[key];
            map[tag] = profile;
            this._settingsDraft.profile_tags = map;
            this._render();
          });
          break;
        case "remove-all-tag":
          this._settingsDraft.all_tag_ids = (this._settingsDraft.all_tag_ids || []).filter((t) => t !== target.dataset.tag);
          this._render();
          break;
        case "remove-profile-tag": {
          const map = { ...(this._settingsDraft.profile_tags || {}) };
          delete map[target.dataset.tag];
          this._settingsDraft.profile_tags = map;
          this._render();
          break;
        }
        case "stop-scan":
          this._stopScan();
          this._render();
          break;
        case "save-settings":
          this._run(
            {
              type: "medication_tracker/save_settings",
              default_notify_service: this._settingsDraft.default_notify_service || null,
              fallback_notify_service: this._settingsDraft.fallback_notify_service || null,
              all_tag_ids: this._settingsDraft.all_tag_ids || [],
              profile_tags: this._settingsDraft.profile_tags || {},
            },
            "Settings saved"
          );
          break;
        default:
          break;
      }
    }

    _onInput(event) {
      const el = event.target;
      if (el.dataset.day !== undefined && this._form) {
        const day = Number(el.dataset.day);
        const days = new Set(this._form.days);
        if (el.checked) days.add(day);
        else days.delete(day);
        this._form.days = [...days].sort();
        return;
      }
      if (el.dataset.time !== undefined && this._form) {
        this._form.schedules[Number(el.dataset.time)] = el.value;
        return;
      }
      if (el.dataset.field && this._form) {
        this._form[el.dataset.field] = el.type === "checkbox" ? el.checked : el.value;
        if (el.dataset.field === "medication_name") this._maybeFillFromDatabase(el.value);
        return;
      }
      if (el.dataset.setting && this._settingsDraft) {
        this._settingsDraft[el.dataset.setting] = el.value || null;
      }
      if (el.dataset.profileTag !== undefined && this._settingsDraft) {
        const profile = el.dataset.profileTag;
        const map = { ...(this._settingsDraft.profile_tags || {}) };
        for (const key of Object.keys(map)) if (map[key] === profile) delete map[key];
        if (el.value.trim()) map[el.value.trim()] = profile;
        this._settingsDraft.profile_tags = map;
      }
    }

    _maybeFillFromDatabase(name) {
      const entry = (this._state.database || []).find((item) => (item.name || "").toLowerCase() === name.toLowerCase());
      if (!entry || this._form.medication_id) return;
      this._form.database_entry_id = entry.id;
      if (!this._form.purpose) this._form.purpose = entry.purpose || "";
      if (!this._form.form) this._form.form = entry.form || "";
    }

    // ------------------------------------------------------------- NFC scan

    async _startScan(onTag) {
      this._stopScan();
      try {
        this._scan = { pending: true };
        this._render();
        const unsub = await this._hass.connection.subscribeEvents((ev) => {
          const tag = ev.data && ev.data.tag_id;
          if (!tag) return;
          this._stopScan();
          onTag(tag);
          this._say("Tag captured");
        }, "tag_scanned");
        if (this._scan) this._scan.unsub = unsub;
        else unsub();
      } catch (err) {
        this._scan = null;
        this._say("Could not listen for tags: " + ((err && err.message) || err), true);
      }
    }

    _stopScan() {
      if (this._scan && this._scan.unsub) this._scan.unsub();
      this._scan = null;
    }

    // ------------------------------------------------------------------ save

    _saveForm() {
      const f = this._form;
      if (!f.profile_name.trim()) return this._say("Who is this medication for?", true);
      if (!f.medication_name.trim()) return this._say("Enter the medication name", true);
      if (!f.schedules.length || f.schedules.some((t) => !t)) return this._say("Add at least one time", true);
      if (!f.days.length) return this._say("Choose at least one day", true);
      const msg = {
        type: "medication_tracker/save_medication",
        medication_id: f.medication_id || null,
        profile_name: f.profile_name.trim(),
        medication_name: f.medication_name.trim(),
        dosage: f.dosage.trim() || "1 dose",
        schedules: f.schedules,
        days_of_week: f.days.length === 7 ? null : f.days,
        quantity: num(f.quantity),
        refill_at: num(f.refill_at),
        notes: f.notes,
        instructions: f.instructions,
        purpose: f.purpose,
        form: f.form,
        nfc_tag_id: f.nfc_tag_id.trim() || null,
        notification_enabled: !!f.notification_enabled,
        notify_service: f.notify_service || null,
        caregiver_name: f.caregiver_name.trim() || null,
        caregiver_notify_service: f.caregiver_notify_service.trim() || null,
        confirmation_required: !!f.confirmation_required,
        reminder_minutes: Number(f.reminder_minutes) || 15,
        missed_after_minutes: Number(f.missed_after_minutes) || 60,
        duplicate_guard_minutes: Number(f.duplicate_guard_minutes) || 0,
        repeat_every_minutes: Number(f.repeat_every_minutes) || 0,
        max_repeats: Number(f.max_repeats) || 0,
        database_entry_id: f.database_entry_id || null,
      };
      this._run(msg, "Saved").then((result) => {
        if (result) {
          this._stopScan();
          this._form = null;
          this._render();
        }
      });
    }

    // ---------------------------------------------------------------- render

    _render() {
      const root = this.shadowRoot;
      if (!root) return;
      let body;
      if (this._loadError && !this._state) {
        body = `<div class="card"><h2>Medication Tracker</h2><p>${esc(this._loadError)}</p></div>`;
      } else if (!this._state) {
        body = `<div class="empty">Loading…</div>`;
      } else if (this._tab === "today") {
        body = this._renderToday();
      } else if (this._tab === "medications") {
        body = this._form ? this._renderForm() : this._renderMedications();
      } else if (this._tab === "history") {
        body = this._renderHistory();
      } else {
        body = this._renderSettings();
      }
      const tabs = [
        ["today", "Today"],
        ["medications", "Medications"],
        ["history", "History"],
        ["settings", "Settings"],
      ]
        .map(([key, label]) => `<button class="tab ${this._tab === key ? "active" : ""}" data-action="tab" data-tab="${key}">${label}</button>`)
        .join("");
      const toast = this._toast ? `<div class="toast ${this._toast.error ? "err" : ""}">${esc(this._toast.message)}</div>` : "";
      const scrollTop = this.scrollTop;
      root.innerHTML = `<style>${STYLE}</style>
        <div class="bar">${this._narrow ? '<button class="menu" data-action="menu" aria-label="Menu">☰</button>' : ""}<h1>Medications</h1></div>
        <div class="tabs">${tabs}</div>
        <main>${body}</main>${toast}`;
      this.scrollTop = scrollTop;
    }

    _renderToday() {
      const s = this._state;
      const doses = s.today || [];
      if (!s.medications.length) {
        return `<div class="card empty"><p>No medications yet.</p>${
          this._isAdmin ? '<button class="btn big" data-action="add">Add your first medication</button>' : ""
        }</div>`;
      }
      const outstanding = s.summary.outstanding_count || 0;
      const needsRefill = s.medications.filter((m) => m.needs_refill);
      const parts = [];
      parts.push(`<div class="card hero"><div><h2 style="margin:0">${
        outstanding ? `${outstanding} to take now` : "Nothing due right now"
      }</h2><div class="sub">${s.summary.next_due ? "Next dose " + esc(fmtDateTime(s.summary.next_due)) : "No upcoming doses"}</div></div>${
        outstanding ? '<button class="btn big" data-action="take-all">✓ Take all due</button>' : ""
      }</div>`);
      if (needsRefill.length) {
        parts.push(`<div class="banner">Running low: ${needsRefill
          .map((m) => `${esc(m.medication_name)} (${esc(m.remaining_quantity)} left)`)
          .join(", ")}</div>`);
      }
      const byProfile = {};
      for (const dose of doses) (byProfile[dose.profile_name] ||= { id: dose.profile_id, doses: [] }).doses.push(dose);
      if (!doses.length) parts.push(`<div class="card empty">Nothing scheduled today.</div>`);
      for (const [name, group] of Object.entries(byProfile)) {
        const canTake = group.doses.filter((d) => d.can_take).length;
        const rows = group.doses
          .map((d) => {
            const cls = STATUS_CLASS[d.status] || "muted";
            const label = STATUS_LABEL[d.status] || d.status;
            const actions = d.can_take
              ? `<div class="actions"><button class="btn" data-action="take" data-id="${esc(d.medication_id)}">Taken</button>
                 <button class="btn secondary" data-action="snooze" data-id="${esc(d.medication_id)}" data-minutes="10">Snooze 10m</button>
                 <button class="btn secondary" data-action="skip" data-id="${esc(d.medication_id)}">Skip</button></div>`
              : "";
            return `<div class="row"><span class="time">${esc(d.time)}</span>
              <div class="grow"><div>${esc(d.medication_name)}</div><div class="sub">${esc(d.dosage)}</div></div>
              <span class="chip ${cls}">${esc(label)}</span>${actions}</div>`;
          })
          .join("");
        const allBtn =
          canTake > 1
            ? `<button class="btn secondary" data-action="take-all" data-profile="${esc(group.id)}">All taken for ${esc(name)}</button>`
            : "";
        parts.push(`<div class="card"><div class="hero"><h2>${esc(name)}</h2>${allBtn}</div>${rows}</div>`);
      }
      return parts.join("");
    }

    _renderMedications() {
      const s = this._state;
      const admin = this._isAdmin;
      const header = `<div class="hero" style="margin-bottom:12px"><div class="sub">${s.medications.length} medication${
        s.medications.length === 1 ? "" : "s"
      }</div>${admin ? '<button class="btn" data-action="add">+ Add medication</button>' : ""}</div>`;
      if (!s.medications.length) {
        return header + `<div class="card empty">No medications yet.</div>`;
      }
      const cards = s.medications
        .map((m) => {
          const days = m.days_of_week && m.days_of_week.length ? m.days_of_week.map((d) => DAYS[d]).join(", ") : "Every day";
          const stock =
            m.remaining_quantity === null || m.remaining_quantity === undefined
              ? "Stock not tracked"
              : `${m.remaining_quantity} left${m.days_remaining !== null ? ` (~${m.days_remaining} days)` : ""}`;
          return `<div class="card">
            <div class="hero"><div><h2 style="margin:0">${esc(m.medication_name)} <span class="sub">${esc(m.dosage)}</span></h2>
            <div class="sub">${esc(m.profile_name)}${m.purpose ? " · " + esc(m.purpose) : ""}</div></div>
            ${m.needs_refill ? '<span class="chip warn">Refill needed</span>' : ""}</div>
            <div class="sub" style="margin-top:8px">⏰ ${esc((m.schedules || []).join(", "))} · ${esc(days)}</div>
            <div class="sub">📦 ${esc(stock)}${m.nfc_tag_id ? " · 🏷 NFC tag set" : ""}</div>
            <div class="sub">Next: ${esc(fmtDateTime(m.next_dose))} · Last taken: ${esc(fmtDateTime(m.last_taken))}</div>
            <div class="actions" style="margin-top:12px">
              <button class="btn secondary" data-action="refill" data-id="${esc(m.medication_id)}">Add stock</button>
              ${admin ? `<button class="btn secondary" data-action="edit" data-id="${esc(m.medication_id)}">Edit</button>
              <button class="btn danger" data-action="delete" data-id="${esc(m.medication_id)}">Delete</button>` : ""}
            </div></div>`;
        })
        .join("");
      return header + cards;
    }

    _notifyOptions(selected, blankLabel) {
      const services = this._state.notify_services || [];
      const list = selected && !services.includes(selected) ? [selected, ...services] : services;
      return (
        `<option value="">${esc(blankLabel)}</option>` +
        list.map((svc) => `<option value="${esc(svc)}" ${svc === selected ? "selected" : ""}>${esc(svc)}</option>`).join("")
      );
    }

    _renderForm() {
      const f = this._form;
      const editing = !!f.medication_id;
      const profiles = Object.values(this._state.profiles || {});
      const defaultNotify = this._state.settings.default_notify_service;
      const times = f.schedules
        .map(
          (t, i) => `<span><input type="time" value="${esc(t)}" data-time="${i}">${
            f.schedules.length > 1 ? `<button class="btn danger" style="padding:4px 10px" data-action="remove-time" data-index="${i}" aria-label="Remove time">×</button>` : ""
          }</span>`
        )
        .join("");
      const days = DAYS.map(
        (label, i) => `<label><input type="checkbox" data-day="${i}" ${f.days.includes(i) ? "checked" : ""}><span>${label}</span></label>`
      ).join("");
      const scanning = this._scan ? `<div class="banner">Hold your phone to the NFC tag now… <button class="btn secondary" data-action="stop-scan">Cancel</button></div>` : "";
      const field = (key, label, attrs = "") =>
        `<label class="field">${label}<input data-field="${key}" value="${esc(f[key])}" ${attrs}></label>`;
      return `<div class="card"><h2>${editing ? "Edit medication" : "Add medication"}</h2>
        <datalist id="profiles">${profiles.map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
        <datalist id="meds">${(this._state.database || []).map((d) => `<option value="${esc(d.name)}">`).join("")}</datalist>
        <div class="grid">
          ${field("profile_name", "Who is it for?", 'list="profiles" placeholder="e.g. Mike"')}
          ${field("medication_name", "Medication", 'list="meds" placeholder="e.g. Vitamin D"')}
          ${field("dosage", "Dose", 'placeholder="e.g. 1 tablet"')}
        </div>
        <h2 style="margin-top:16px">When</h2>
        <div class="times">${times}<button class="btn secondary" data-action="add-time">+ Add time</button></div>
        <div class="days" style="margin-top:12px">${days}</div>
        <h2 style="margin-top:16px">Stock</h2>
        <div class="grid">
          ${field("quantity", "Doses left (optional)", 'type="number" min="0" step="1"')}
          ${field("refill_at", "Warn me at (doses)", 'type="number" min="0" step="1"')}
        </div>
        <h2 style="margin-top:16px">Taking it</h2>
        ${scanning}
        <div class="grid">
          <label class="field">NFC tag ID (optional)<span style="display:flex;gap:6px"><input style="flex:1" data-field="nfc_tag_id" value="${esc(f.nfc_tag_id)}" placeholder="scan or paste"><button class="btn secondary" data-action="scan-form" type="button">Scan</button></span></label>
          <label class="field">Phone to notify<select data-field="notify_service">${this._notifyOptions(
            f.notify_service,
            defaultNotify ? `Use default (${defaultNotify})` : "Use default (set in Settings)"
          )}</select></label>
        </div>
        <label class="field" style="margin-top:12px;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" data-field="notification_enabled" ${f.notification_enabled ? "checked" : ""}> Send reminders</label>
        <details><summary>More options</summary>
          <div class="grid" style="margin-top:12px">
            ${field("repeat_every_minutes", "Repeat reminder every (min, 0 = never)", 'type="number" min="0" max="240"')}
            ${field("max_repeats", "Max repeats", 'type="number" min="0" max="20"')}
            ${field("reminder_minutes", "Reminder stays active (min)", 'type="number" min="1"')}
            ${field("missed_after_minutes", "Count as missed after (min)", 'type="number" min="1"')}
            ${field("duplicate_guard_minutes", "Block double-logging for (min)", 'type="number" min="0"')}
            ${field("purpose", "Purpose")}
            ${field("instructions", "Instructions")}
            ${field("notes", "Notes")}
            ${field("caregiver_name", "Caregiver name")}
            <label class="field">Caregiver notify service<select data-field="caregiver_notify_service">${this._notifyOptions(f.caregiver_notify_service, "Same as above")}</select></label>
          </div>
          <label class="field" style="margin-top:12px;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" data-field="confirmation_required" ${f.confirmation_required ? "checked" : ""}> Caregiver must confirm each dose</label>
        </details>
        <div class="actions" style="margin-top:20px">
          <button class="btn big" data-action="save">Save</button>
          <button class="btn secondary big" data-action="cancel">Cancel</button>
          ${editing ? `<button class="btn secondary" data-action="test" data-id="${esc(f.medication_id)}">Send test notification</button>
          <button class="btn danger" data-action="reset-history" data-id="${esc(f.medication_id)}">Reset history</button>` : ""}
        </div></div>`;
    }

    _renderHistory() {
      const logs = this._state.recent_logs || [];
      if (!logs.length) return `<div class="card empty">No doses logged yet.</div>`;
      const admin = this._isAdmin;
      const rows = logs
        .map(
          (l) => `<tr><td>${esc(fmtDateTime(l.taken_at))}</td><td>${esc(l.profile_name)}</td><td>${esc(l.medication_name)}</td>
            <td class="hide-narrow">${esc(l.source)}</td>
            <td>${admin ? `<button class="btn danger" style="padding:4px 10px" data-action="delete-dose" data-id="${esc(l.medication_id)}" data-taken-at="${esc(l.taken_at)}">Delete</button>` : ""}</td></tr>`
        )
        .join("");
      return `<div class="card"><h2>Recent doses</h2><table><tr><th>When</th><th>Who</th><th>Medication</th><th class="hide-narrow">Via</th><th></th></tr>${rows}</table></div>`;
    }

    _renderSettings() {
      const d = this._settingsDraft || this._state.settings;
      const admin = this._isAdmin;
      const profiles = this._state.profiles || {};
      const allTags = (d.all_tag_ids || [])
        .map((t) => `<div class="row"><div class="grow"><code>${esc(t)}</code></div><button class="btn danger" data-action="remove-all-tag" data-tag="${esc(t)}">Remove</button></div>`)
        .join("");
      const profileTags = Object.entries(profiles)
        .map(([pid, name]) => {
          const tag = Object.entries(d.profile_tags || {}).find(([, p]) => p === pid);
          return `<div class="row"><div class="grow"><div>${esc(name)}</div></div>
            <input data-profile-tag="${esc(pid)}" value="${esc(tag ? tag[0] : "")}" placeholder="tag ID">
            <button class="btn secondary" data-action="scan-profile" data-profile="${esc(pid)}">Scan</button></div>`;
        })
        .join("");
      const scanning = this._scan ? `<div class="banner">Hold your phone to the NFC tag now… <button class="btn secondary" data-action="stop-scan">Cancel</button></div>` : "";
      return `<div class="card"><h2>Notifications</h2>
          <div class="sub" style="margin-bottom:12px">Pick the phone that should get reminders. Each medication can override this.</div>
          <div class="grid">
            <label class="field">Default phone<select data-setting="default_notify_service" ${admin ? "" : "disabled"}>${this._notifyOptions(d.default_notify_service, "None")}</select></label>
            <label class="field">Backup phone (if the first fails)<select data-setting="fallback_notify_service" ${admin ? "" : "disabled"}>${this._notifyOptions(d.fallback_notify_service, "None")}</select></label>
          </div></div>
        <div class="card"><h2>NFC tags</h2>${scanning}
          <div class="sub" style="margin-bottom:8px">Write a tag in the Companion app (Settings → Tags), then press Scan here and tap it. A medication's own tag is set on its edit page.</div>
          <h2 style="margin-top:12px;font-size:14px">Tags that mark everything due as taken</h2>${allTags || '<div class="sub">None yet.</div>'}
          ${admin ? '<div style="margin-top:8px"><button class="btn secondary" data-action="scan-all">Scan a tag to add</button></div>' : ""}
          ${profileTags ? `<h2 style="margin-top:16px;font-size:14px">Tag per person (marks only their medications taken)</h2>${profileTags}` : ""}
        </div>
        ${admin ? '<div class="actions"><button class="btn big" data-action="save-settings">Save settings</button></div>' : '<div class="sub">Only administrators can change settings.</div>'}
        <div class="sub" style="margin-top:16px">Medication Tracker v${esc(this._state.version)}</div>`;
    }
  }

  customElements.define("medication-tracker-panel", MedicationTrackerPanel);
})();
