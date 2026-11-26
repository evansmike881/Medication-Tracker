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
    as_needed: false,
    max_doses_per_day: "",
    interval_days: 1,
    anchor_date: "",
    end_date: "",
    escalate_after_minutes: 0,
    group_id: "",
    food_note: "",
    keep_apart: [],
    keep_apart_minutes: 120,
  });

  const blankGroup = (profiles) => ({
    group_id: null,
    profile_name: Object.values(profiles || {}).length === 1 ? Object.values(profiles)[0] : "",
    name: "",
    schedules: ["08:00"],
    days: [0, 1, 2, 3, 4, 5, 6],
    interval_days: 1,
    anchor_date: "",
    notify_service: "",
    nfc_tag_id: "",
    notification_enabled: true,
    member_ids: [],
  });

  const blankQuick = (profiles) => ({
    profile_name: Object.values(profiles || {}).length === 1 ? Object.values(profiles)[0] : "",
    group_choice: "new",
    new_name: "",
    schedules: ["08:00"],
    text: "",
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
    as_needed: !!s.as_needed,
    max_doses_per_day: s.max_doses_per_day ?? "",
    interval_days: s.interval_days ?? 1,
    anchor_date: s.anchor_date || "",
    end_date: s.end_date || "",
    escalate_after_minutes: s.escalate_after_minutes ?? 0,
    group_id: s.group_id || "",
    food_note: s.food_note || "",
    keep_apart: [...(s.keep_apart || [])],
    keep_apart_minutes: s.keep_apart_minutes || 120,
  });

  const store = {
    get(key) {
      try {
        return window.localStorage.getItem(key);
      } catch (_err) {
        return null;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, value);
      } catch (_err) {
        /* private mode: the setting just won't stick */
      }
    },
  };

  const FOOD = { with_food: "with food", empty_stomach: "empty stomach" };
  const TEMPLATES = [
    ["Everyday vitamins", ["Vitamin D", "Vitamin C", "Vitamin B12", "Multivitamin"]],
    ["Minerals", ["Magnesium", "Zinc", "Calcium", "Iron"]],
    ["Joint and heart", ["Omega 3", "Glucosamine", "CoQ10"]],
  ];
  const todayIso = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };

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
    .handle { cursor:grab; touch-action:none; user-select:none; -webkit-user-select:none; background:none; border:0; color:var(--secondary-text-color); font-size:20px; line-height:1; padding:8px 6px; border-radius:6px; min-width:34px; min-height:38px; }
    .handle:focus-visible { outline:2px solid var(--primary-color); }
    .dragging { opacity:.35; }
    .ghost { position:fixed; z-index:50; pointer-events:none; background:var(--card-background-color,#fff); border:1px solid var(--primary-color); border-radius:8px; padding:8px 14px; box-shadow:0 6px 18px rgba(0,0,0,.3); max-width:80vw; }
    .dropline { height:4px; border-radius:2px; background:var(--primary-color); margin:2px 0; pointer-events:none; }
    .zone { border:2px dashed transparent; border-radius:10px; padding:2px; min-height:40px; }
    .zone.over { border-color:var(--primary-color); background:rgba(3,169,244,.08); }
    .zone.ungrouped { border-color:var(--divider-color); }
    .gcard { border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; margin-bottom:10px; }
    .gcard.over { border-color:var(--primary-color); }
    .mrow { display:flex; align-items:center; gap:8px; padding:6px 0; border-top:1px solid var(--divider-color); flex-wrap:wrap; }
    .mrow.first { border-top:0; }
    .emptyhint { color:var(--secondary-text-color); font-size:13px; padding:10px; text-align:center; }
    .block { border:1px solid var(--divider-color); border-radius:10px; margin:8px 0; padding:4px 10px; }
    .bhead { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:6px 0; }
    .bar2 { height:6px; border-radius:3px; background:var(--divider-color); overflow:hidden; min-width:80px; flex:1; }
    .bar2 > i { display:block; height:100%; background:#43a047; }
    .memberlist label { display:flex; gap:8px; align-items:center; padding:6px 0; color:var(--primary-text-color); font-size:14px; }
    textarea { width:100%; min-height:140px; }
    .hint { background:rgba(3,169,244,.1); border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:13px; }
    .linkbtn { background:none; border:0; font:inherit; color:inherit; cursor:pointer; padding:4px 2px; text-align:left; display:flex; align-items:center; gap:8px; min-width:0; }
    .chev { display:inline-block; width:18px; transition:transform .15s; color:var(--secondary-text-color); }
    .collapsed-sum { color:var(--secondary-text-color); font-size:13px; }
    .zone.collapsed .mrow, .zone.collapsed .emptyhint { display:none; }
    .zone.collapsed { min-height:14px; padding:0; }
    .zone.nope { border-color:var(--error-color,#c62828); background:rgba(198,40,40,.08); }
    .search { width:100%; margin-bottom:12px; }
    .tag { font-size:11px; padding:2px 8px; border-radius:10px; background:rgba(3,169,244,.14); color:var(--primary-text-color); white-space:nowrap; }
    .warnline { color:#b26a00; font-size:12px; }
    .iconbtn { background:none; border:1px solid rgba(255,255,255,.5); color:inherit; border-radius:16px; padding:4px 10px; cursor:pointer; font:inherit; font-size:13px; }
    .large button.btn { padding:14px 22px; font-size:17px; }
    .large .handle { font-size:26px; min-width:48px; min-height:52px; }
    .large .row, .large .mrow { padding:14px 0; font-size:17px; }
    .large .sub { font-size:15px; }
    .large input, .large select { font-size:17px; padding:12px; }
    .report h3 { margin:16px 0 6px; }
    .report table { margin-bottom:8px; }
    @media print { .bar, .tabs, .noprint, .toastbox { display:none !important; } :host { background:#fff; color:#000; } main { max-width:none; padding:0; } .card { box-shadow:none; border:1px solid #ccc; break-inside:avoid; } }
    @media (max-width:600px) { main { padding:8px; } .hide-narrow { display:none; } }
  `;

  class MedicationTrackerPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._state = null;
      this._tab = "today";
      this._form = null;
      this._gform = null;
      this._quick = null;
      this._drag = null;
      this._pauseForm = null;
      this._report = false;
      this._search = "";
      this._todayOpen = {};
      let collapsed = [];
      try {
        collapsed = JSON.parse(store.get("mt_collapsed") || "[]");
      } catch (_err) {
        collapsed = [];
      }
      this._collapsed = new Set(Array.isArray(collapsed) ? collapsed : []);
      const savedLarge = store.get("mt_large");
      this._large =
        savedLarge === null
          ? !!(window.matchMedia && window.matchMedia("(pointer: coarse) and (min-width: 700px)").matches)
          : savedLarge === "1";
      this._settingsDraft = null;
      this._toast = null;
      this._scan = null;
      this._busy = false;
      this._timer = null;
      this._narrow = false;
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
      this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("change", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("pointerdown", (e) => this._onPointerDown(e));
      this.shadowRoot.addEventListener("keydown", (e) => this._onKeyDown(e));
    }

    get _editing() {
      return this._form || this._gform || this._quick || this._pauseForm;
    }

    _saveCollapsed() {
      store.set("mt_collapsed", JSON.stringify([...this._collapsed]));
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
      this._endDrag(false);
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
      if (this._editing || this._drag || this._tab === "settings") return;
      this._load();
    }

    _toastHtml() {
      return this._toast ? `<div class="toast ${this._toast.error ? "err" : ""}">${esc(this._toast.message)}</div>` : "";
    }

    _say(message, error = false) {
      // Only touch the toast element: re-rendering everything would steal focus from a field being typed in.
      this._toast = { message, error };
      const box = this.shadowRoot.querySelector(".toastbox");
      if (box) box.innerHTML = this._toastHtml();
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this._toast = null;
        const el = this.shadowRoot.querySelector(".toastbox");
        if (el) el.innerHTML = "";
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
          this._gform = null;
          this._quick = null;
          this._pauseForm = null;
          this._report = false;
          if (tab === "settings") this._settingsDraft = JSON.parse(JSON.stringify(this._state.settings));
          this._render();
          break;
        case "take":
          this._run({ type: "medication_tracker/take", medication_id: id }, "Marked as taken").then((r) => {
            if (r && r.warnings && r.warnings.length) this._say(r.warnings[0], true);
          });
          break;
        case "toggle-group":
          if (this._collapsed.has(id)) this._collapsed.delete(id);
          else this._collapsed.add(id);
          this._saveCollapsed();
          this._render();
          break;
        case "collapse-all":
          for (const g of this._state.groups || []) this._collapsed.add(g.group_id);
          this._saveCollapsed();
          this._render();
          break;
        case "expand-all":
          this._collapsed.clear();
          this._saveCollapsed();
          this._render();
          break;
        case "toggle-block": {
          const key = target.dataset.key;
          this._todayOpen[key] = !(target.dataset.open === "1");
          this._render();
          break;
        }
        case "toggle-large":
          this._large = !this._large;
          store.set("mt_large", this._large ? "1" : "0");
          this._render();
          break;
        case "duplicate": {
          const snap = this._state.medications.find((m) => m.medication_id === id);
          if (snap) {
            this._form = { ...formFromSnapshot(snap), medication_id: null, medication_name: `${snap.medication_name} (copy)`, quantity: "", nfc_tag_id: "", database_entry_id: null };
            this._tab = "medications";
            this._render();
          }
          break;
        }
        case "template": {
          const tpl = TEMPLATES[Number(index)];
          if (tpl && this._quick) {
            const have = this._quick.text.trim() ? this._quick.text.replace(/\s+$/, "") + "\n" : "";
            this._quick.text = have + tpl[1].map((n) => `${n}, 1 tablet`).join("\n");
            this._render();
          }
          break;
        }
        case "pause-open":
          this._pauseForm = { profile_id: "", start: todayIso(), end: "" };
          this._render();
          break;
        case "pause-save": {
          const f = this._pauseForm;
          if (!f.end) return this._say("Choose the last day of the pause", true);
          if (f.end < f.start) return this._say("The pause cannot end before it starts", true);
          this._run(
            { type: "medication_tracker/add_pause", profile_id: f.profile_id || null, start: f.start || null, end: f.end },
            "Reminders paused"
          ).then((r) => {
            if (r) {
              this._pauseForm = null;
              this._render();
            }
          });
          break;
        }
        case "resume":
          this._run({ type: "medication_tracker/remove_pause", index: Number(index) }, "Reminders resumed");
          break;
        case "report-open":
          this._report = true;
          this._render();
          break;
        case "report-close":
          this._report = false;
          this._render();
          break;
        case "print":
          window.print();
          break;
        case "backup-download":
          this._downloadBackup();
          break;
        case "backup-restore":
          this.shadowRoot.querySelector("input[data-restore]")?.click();
          break;
        case "take-all":
          this._run(
            { type: "medication_tracker/take_all", ...(profile ? { profile_id: profile } : {}) },
            "Marked everything due as taken"
          );
          break;
        case "take-group":
          this._run(
            { type: "medication_tracker/take_all", medication_ids: (target.dataset.ids || "").split(",").filter(Boolean) },
            `Marked ${target.dataset.label || "the group"} as taken`
          );
          break;
        case "new-group":
          this._tab = "medications";
          this._form = null;
          this._quick = null;
          this._gform = blankGroup(this._state.profiles);
          this._render();
          break;
        case "edit-group": {
          const g = (this._state.groups || []).find((x) => x.group_id === id);
          if (g) {
            this._gform = {
              group_id: g.group_id,
              profile_name: g.profile_name,
              name: g.name,
              schedules: [...g.schedules],
              days: g.days_of_week && g.days_of_week.length ? [...g.days_of_week] : [0, 1, 2, 3, 4, 5, 6],
              interval_days: g.interval_days || 1,
              anchor_date: g.anchor_date || "",
              notify_service: g.notify_service || "",
              nfc_tag_id: g.nfc_tag_id || "",
              notification_enabled: g.notification_enabled !== false,
              member_ids: [...(g.member_ids || [])],
            };
            this._render();
          }
          break;
        }
        case "save-group":
          this._saveGroup();
          break;
        case "delete-group": {
          const g = (this._state.groups || []).find((x) => x.group_id === id);
          if (g && window.confirm(`Delete the group ${g.name}? Its medications are kept and keep their current times.`)) {
            this._run({ type: "medication_tracker/delete_group", group_id: id }, "Group deleted").then((r) => {
              if (r) {
                this._gform = null;
                this._render();
              }
            });
          }
          break;
        }
        case "quick-add":
          this._tab = "medications";
          this._form = null;
          this._gform = null;
          this._quick = blankQuick(this._state.profiles);
          this._render();
          break;
        case "save-quick":
          this._saveQuick();
          break;
        case "take-earlier": {
          const answer = window.prompt("What time did you take it today? (HH:MM, 24-hour)", "");
          const match = /^(\d{1,2}):(\d{2})$/.exec((answer || "").trim());
          if (!match) {
            if (answer) this._say("Please enter a time like 08:15", true);
            break;
          }
          const when = new Date();
          when.setHours(Number(match[1]), Number(match[2]), 0, 0);
          if (when > new Date()) when.setDate(when.getDate() - 1);
          this._run(
            { type: "medication_tracker/take", medication_id: id, taken_at: when.toISOString() },
            "Marked as taken"
          );
          break;
        }
        case "undo":
          if (window.confirm("Undo the last logged dose of this medication?")) {
            this._run({ type: "medication_tracker/undo_last", medication_id: id }, "Dose undone");
          }
          break;
        case "export-csv":
          this._exportCsv();
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
          this._gform = null;
          this._quick = null;
          this._pauseForm = null;
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
          this._cur().schedules.push("12:00");
          this._render();
          break;
        case "remove-time":
          if (this._cur().schedules.length > 1) {
            this._cur().schedules.splice(Number(index), 1);
            this._render();
          }
          break;
        case "scan-form": {
          const target_form = this._cur();
          this._startScan((tag) => {
            target_form.nfc_tag_id = tag;
            this._render();
          });
          break;
        }
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
              escalation_notify_service: this._settingsDraft.escalation_notify_service || null,
              critical_notifications: this._settingsDraft.critical_notifications !== false,
              announce_service: this._settingsDraft.announce_service || null,
              announce_only_when_home_entity: this._settingsDraft.announce_only_when_home_entity || null,
              quiet_hours_start: this._settingsDraft.quiet_hours_start || null,
              quiet_hours_end: this._settingsDraft.quiet_hours_end || null,
              profile_notify_services: this._settingsDraft.profile_notify_services || {},
              weekly_summary_service: this._settingsDraft.weekly_summary_service || null,
              weekly_summary_day: Number(this._settingsDraft.weekly_summary_day ?? 6),
            },
            "Settings saved"
          );
          break;
        default:
          break;
      }
    }

    _cur() {
      return this._gform || this._quick || this._form;
    }

    _profileIdByName(name) {
      const wanted = (name || "").trim().toLowerCase();
      const hit = Object.entries(this._state.profiles || {}).find(([, n]) => n.toLowerCase() === wanted);
      return hit ? hit[0] : null;
    }

    _groupsFor(profileName) {
      const pid = this._profileIdByName(profileName);
      return pid ? (this._state.groups || []).filter((g) => g.profile_id === pid) : [];
    }

    _refreshDependent() {
      const f = this._cur();
      const root = this.shadowRoot;
      if (!f) return;
      if (this._form) {
        const sel = root.querySelector("select[data-field=group_id]");
        const groups = this._groupsFor(f.profile_name);
        if (f.group_id && !groups.some((g) => g.group_id === f.group_id)) f.group_id = "";
        if (sel) sel.innerHTML = this._groupOptions(groups, f.group_id, "No group");
        const apart = root.querySelector(".apartlist");
        if (apart) apart.innerHTML = this._apartListHtml();
      } else if (this._quick) {
        const sel = root.querySelector("select[data-field=group_choice]");
        const groups = this._groupsFor(f.profile_name);
        if (f.group_choice !== "new" && f.group_choice !== "" && !groups.some((g) => g.group_id === f.group_choice)) f.group_choice = "new";
        if (sel) sel.innerHTML = this._quickGroupOptions(groups, f.group_choice);
      } else if (this._gform) {
        const box = root.querySelector(".memberlist");
        if (box) box.innerHTML = this._memberListHtml();
      }
    }

    _onInput(event) {
      const el = event.target;
      if (el.dataset.restore !== undefined) {
        const file = el.files && el.files[0];
        if (file) this._restoreBackup(file);
        el.value = "";
        return;
      }
      if (el.dataset.search !== undefined) {
        this._search = el.value;
        const list = this.shadowRoot.querySelector(".medlist");
        if (list) list.innerHTML = this._medListHtml();
        return;
      }
      if (el.dataset.pause && this._pauseForm) {
        this._pauseForm[el.dataset.pause] = el.value;
        return;
      }
      if (el.dataset.apart !== undefined && this._form) {
        const set = new Set(this._form.keep_apart);
        if (el.checked) set.add(el.dataset.apart);
        else set.delete(el.dataset.apart);
        this._form.keep_apart = [...set];
        return;
      }
      if (el.dataset.profilePhone !== undefined && this._settingsDraft) {
        const map = { ...(this._settingsDraft.profile_notify_services || {}) };
        if (el.value) map[el.dataset.profilePhone] = el.value;
        else delete map[el.dataset.profilePhone];
        this._settingsDraft.profile_notify_services = map;
        return;
      }
      const f = this._cur();
      if (el.dataset.day !== undefined && f) {
        const day = Number(el.dataset.day);
        const days = new Set(f.days);
        if (el.checked) days.add(day);
        else days.delete(day);
        f.days = [...days].sort();
        return;
      }
      if (el.dataset.time !== undefined && f) {
        f.schedules[Number(el.dataset.time)] = el.value;
        return;
      }
      if (el.dataset.member !== undefined && this._gform) {
        const set = new Set(this._gform.member_ids);
        if (el.checked) set.add(el.dataset.member);
        else set.delete(el.dataset.member);
        this._gform.member_ids = [...set];
        return;
      }
      if (el.dataset.field && f) {
        f[el.dataset.field] = el.type === "checkbox" ? el.checked : el.value;
        const field = el.dataset.field;
        if (field === "as_needed" && el.checked && this._form) this._form.group_id = "";
        if (["as_needed", "group_id", "group_choice"].includes(field) && event.type === "change") this._render();
        if (field === "profile_name") this._refreshDependent();
        if (field === "medication_name" && this._form) this._maybeFillFromDatabase(el.value);
        return;
      }
      if (el.dataset.setting && this._settingsDraft) {
        this._settingsDraft[el.dataset.setting] = el.type === "checkbox" ? el.checked : el.value || null;
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
      if (!f.as_needed && !f.group_id) {
        if (!f.schedules.length || f.schedules.some((t) => !t)) return this._say("Add at least one time", true);
        if (!f.days.length) return this._say("Choose at least one day", true);
      }
      const msg = {
        type: "medication_tracker/save_medication",
        medication_id: f.medication_id || null,
        profile_name: f.profile_name.trim(),
        medication_name: f.medication_name.trim(),
        dosage: f.dosage.trim() || "1 dose",
        schedules: f.as_needed || f.group_id ? [] : f.schedules,
        group_id: f.as_needed ? null : f.group_id || null,
        food_note: f.food_note || "",
        keep_apart: f.keep_apart || [],
        keep_apart_minutes: Number(f.keep_apart_minutes) || 120,
        days_of_week: f.as_needed || f.group_id || f.days.length === 7 ? null : f.days,
        as_needed: !!f.as_needed,
        max_doses_per_day: Number(f.max_doses_per_day) || 0,
        interval_days: Number(f.interval_days) || 1,
        anchor_date: f.anchor_date || null,
        end_date: f.end_date || null,
        escalate_after_minutes: Number(f.escalate_after_minutes) || 0,
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

    _saveGroup() {
      const f = this._gform;
      if (!f.profile_name.trim()) return this._say("Who is this group for?", true);
      if (!f.name.trim()) return this._say("Give the group a name, e.g. Morning vitamins", true);
      if (!f.schedules.length || f.schedules.some((t) => !t)) return this._say("Add at least one time", true);
      if (!f.days.length) return this._say("Choose at least one day", true);
      this._run(
        {
          type: "medication_tracker/save_group",
          group_id: f.group_id || null,
          profile_name: f.profile_name.trim(),
          name: f.name.trim(),
          schedules: f.schedules,
          days_of_week: f.days.length === 7 ? null : f.days,
          interval_days: Number(f.interval_days) || 1,
          anchor_date: f.anchor_date || null,
          notify_service: f.notify_service || null,
          nfc_tag_id: f.nfc_tag_id.trim() || null,
          notification_enabled: !!f.notification_enabled,
          member_ids: f.member_ids,
        },
        "Group saved"
      ).then((result) => {
        if (result) {
          this._stopScan();
          this._gform = null;
          this._render();
        }
      });
    }

    _saveQuick() {
      const f = this._quick;
      if (!f.profile_name.trim()) return this._say("Who are these for?", true);
      const items = f.text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const cut = line.indexOf(",");
          const name = (cut < 0 ? line : line.slice(0, cut)).trim();
          const dosage = cut < 0 ? "" : line.slice(cut + 1).trim();
          return { name, ...(dosage ? { dosage } : {}) };
        })
        .filter((item) => item.name);
      if (!items.length) return this._say("Type one medication per line, e.g. Vitamin D, 1000 IU", true);
      const needsTimes = f.group_choice === "new" || f.group_choice === "";
      if (needsTimes && (!f.schedules.length || f.schedules.some((t) => !t))) return this._say("Add at least one time", true);
      if (f.group_choice === "new" && !f.new_name.trim()) return this._say("Give the new group a name", true);
      const msg = { type: "medication_tracker/quick_add", profile_name: f.profile_name.trim(), items };
      if (f.group_choice === "new") msg.new_group = { name: f.new_name.trim(), schedules: f.schedules };
      else if (f.group_choice) msg.group_id = f.group_choice;
      else msg.schedules = f.schedules;
      this._run(msg, `Added ${items.length} medication${items.length === 1 ? "" : "s"}`).then((result) => {
        if (result) {
          this._quick = null;
          this._render();
        }
      });
    }

    // ------------------------------------------------------- drag and drop

    _onPointerDown(event) {
      const handle = event.target.closest && event.target.closest("[data-drag]");
      if (!handle || !this._isAdmin || this._busy || this._drag) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      const row = handle.closest("[data-row]");
      if (!row) return;
      event.preventDefault();
      const ghost = document.createElement("div");
      ghost.className = "ghost";
      ghost.textContent = row.dataset.label || "";
      this.shadowRoot.appendChild(ghost);
      row.classList.add("dragging");
      try {
        handle.setPointerCapture(event.pointerId);
      } catch (_err) {
        /* not every environment supports capture */
      }
      this._drag = {
        kind: handle.dataset.drag,
        id: handle.dataset.id,
        profile: row.dataset.profile,
        row,
        ghost,
        target: null,
        y: event.clientY,
        scrollers: this._scrollParents(),
      };
      this._dragListeners = {
        move: (e) => this._dragMove(e),
        up: (e) => this._endDrag(true, e),
        cancel: () => this._endDrag(false),
        key: (e) => e.key === "Escape" && this._endDrag(false),
      };
      window.addEventListener("pointermove", this._dragListeners.move);
      window.addEventListener("pointerup", this._dragListeners.up);
      window.addEventListener("pointercancel", this._dragListeners.cancel);
      window.addEventListener("keydown", this._dragListeners.key);
      this._dragMove(event);
      const tick = () => {
        if (!this._drag) return;
        const d = this._drag;
        const edge = 70;
        let delta = 0;
        if (d.y < edge) delta = -Math.ceil((edge - d.y) / 6);
        else if (d.y > window.innerHeight - edge) delta = Math.ceil((d.y - (window.innerHeight - edge)) / 6);
        if (delta) {
          for (const el of d.scrollers) el.scrollTop += delta;
          this._dragMove({ clientX: d.x, clientY: d.y });
        }
        this._dragFrame = requestAnimationFrame(tick);
      };
      this._dragFrame = requestAnimationFrame(tick);
    }

    _scrollParents() {
      const list = [];
      let node = this;
      while (node) {
        if (node.nodeType === 1) {
          const oy = getComputedStyle(node).overflowY;
          if ((oy === "auto" || oy === "scroll") && node.scrollHeight > node.clientHeight) list.push(node);
        }
        node = node.parentNode || node.host;
      }
      if (document.scrollingElement) list.push(document.scrollingElement);
      return list;
    }

    _dragMove(event) {
      const d = this._drag;
      if (!d) return;
      d.x = event.clientX;
      d.y = event.clientY;
      d.ghost.style.left = `${event.clientX + 12}px`;
      d.ghost.style.top = `${event.clientY + 8}px`;
      const root = this.shadowRoot;
      root.querySelectorAll(".dropline").forEach((n) => n.remove());
      root.querySelectorAll(".over, .nope").forEach((n) => n.classList.remove("over", "nope"));
      d.target = null;
      d.foreign = null;
      const under = root.elementFromPoint(event.clientX, event.clientY);
      if (!under) return;
      let container;
      let rows;
      if (d.kind === "med") {
        container = under.closest("[data-zone]");
        if (!container) return;
        if (container.dataset.profile !== d.profile) {
          container.classList.add("nope");
          d.foreign = container.dataset.profile;
          return;
        }
        container.classList.add("over");
        rows = [...container.querySelectorAll('[data-row="med"]')].filter((r) => r !== d.row);
      } else {
        container = under.closest("[data-grouplist]");
        if (!container || container.dataset.profile !== d.profile) return;
        rows = [...container.querySelectorAll(':scope > [data-row="group"]')].filter((r) => r !== d.row);
      }
      let index = 0;
      if (container.classList.contains("collapsed")) {
        index = rows.length; // a folded group: drop at the end
      } else {
        for (const r of rows) {
          const box = r.getBoundingClientRect();
          if (event.clientY > box.top + box.height / 2) index += 1;
        }
      }
      const line = document.createElement("div");
      line.className = "dropline";
      const body = container.querySelector(".zonebody") || container;
      if (rows[index]) rows[index].parentNode.insertBefore(line, rows[index]);
      else if (rows.length) rows[rows.length - 1].parentNode.appendChild(line);
      else body.appendChild(line);
      d.target = { container, index, zone: container.dataset.zone };
    }

    _endDrag(drop, event) {
      const d = this._drag;
      if (!d) return;
      this._drag = null;
      cancelAnimationFrame(this._dragFrame);
      const l = this._dragListeners || {};
      window.removeEventListener("pointermove", l.move);
      window.removeEventListener("pointerup", l.up);
      window.removeEventListener("pointercancel", l.cancel);
      window.removeEventListener("keydown", l.key);
      if (event && drop) {
        this._drag = d; // settle the target at the exact release point
        this._dragMove(event);
        this._drag = null;
      }
      d.ghost.remove();
      d.row.classList.remove("dragging");
      this.shadowRoot.querySelectorAll(".dropline").forEach((n) => n.remove());
      this.shadowRoot.querySelectorAll(".over, .nope").forEach((n) => n.classList.remove("over", "nope"));
      if (drop && !d.target && d.foreign && d.kind === "med") {
        const owner = (this._state.profiles || {})[d.foreign] || "someone else";
        this._say(`That group belongs to ${owner}. A medication can only join a group for the same person.`, true);
      }
      if (!drop || !d.target) return;
      if (d.kind === "med") this._moveMedication(d.id, d.target.zone || null, d.target.index);
      else this._moveGroup(d.id, d.profile, d.target.index);
    }

    _onKeyDown(event) {
      const handle = event.target.closest && event.target.closest("[data-drag]");
      if (!handle || !this._isAdmin) return;
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      const step = event.key === "ArrowUp" ? -1 : 1;
      const id = handle.dataset.id;
      if (handle.dataset.drag === "med") {
        const m = this._state.medications.find((x) => x.medication_id === id);
        if (!m) return;
        const sibs = this._siblings(m);
        const at = sibs.findIndex((x) => x.medication_id === id);
        const to = Math.max(0, Math.min(sibs.length - 1, at + step));
        if (to !== at) this._moveMedication(id, m.group_id || null, to, handle.dataset.id);
      } else {
        const g = (this._state.groups || []).find((x) => x.group_id === id);
        if (!g) return;
        const ids = this._state.groups.filter((x) => x.profile_id === g.profile_id).map((x) => x.group_id);
        const at = ids.indexOf(id);
        const to = Math.max(0, Math.min(ids.length - 1, at + step));
        if (to !== at) this._moveGroup(id, g.profile_id, to, id);
      }
    }

    _siblings(m) {
      return this._state.medications
        .filter((x) => x.profile_id === m.profile_id && (x.group_id || null) === (m.group_id || null) && !x.as_needed)
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.medication_name.localeCompare(b.medication_name));
    }

    async _moveMedication(id, groupId, index, refocus) {
      const m = this._state.medications.find((x) => x.medication_id === id);
      if (!m) return;
      // Update the screen straight away; the server reply then confirms it.
      const wasGroup = m.group_id || null;
      const dest = { ...m, group_id: groupId };
      const sibs = this._siblings(dest).filter((x) => x.medication_id !== id);
      sibs.splice(Math.min(index, sibs.length), 0, m);
      sibs.forEach((x, i) => (x.sort_order = i));
      m.group_id = groupId;
      if (groupId) {
        const g = (this._state.groups || []).find((x) => x.group_id === groupId);
        if (g) {
          for (const gg of this._state.groups) gg.member_ids = (gg.member_ids || []).filter((x) => x !== id);
          const ids = sibs.map((x) => x.medication_id);
          g.member_ids = ids;
          m.schedules = [...g.schedules];
        }
      } else {
        for (const gg of this._state.groups || []) gg.member_ids = (gg.member_ids || []).filter((x) => x !== id);
      }
      this._render();
      if (refocus) this._focusHandle("med", refocus);
      try {
        await this._call({ type: "medication_tracker/move_medication", medication_id: id, group_id: groupId, index });
        if (wasGroup !== groupId) {
          const g = (this._state.groups || []).find((x) => x.group_id === groupId);
          this._say(g ? `Moved to ${g.name}` : "Removed from group");
        }
      } catch (err) {
        this._say((err && err.message) || "Could not move that", true);
      }
      await this._load();
      if (refocus) this._focusHandle("med", refocus);
    }

    async _moveGroup(id, profileId, index, refocus) {
      const ids = (this._state.groups || []).filter((g) => g.profile_id === profileId).map((g) => g.group_id).filter((x) => x !== id);
      ids.splice(Math.min(index, ids.length), 0, id);
      ids.forEach((gid, i) => {
        const g = this._state.groups.find((x) => x.group_id === gid);
        if (g) g.order = i;
      });
      this._state.groups.sort((a, b) => a.profile_name.localeCompare(b.profile_name) || a.order - b.order);
      this._render();
      if (refocus) this._focusHandle("group", refocus);
      try {
        await this._call({ type: "medication_tracker/reorder_groups", profile_id: profileId, group_ids: ids });
      } catch (err) {
        this._say((err && err.message) || "Could not reorder", true);
      }
      await this._load();
      if (refocus) this._focusHandle("group", refocus);
    }

    _focusHandle(kind, id) {
      const el = this.shadowRoot.querySelector(`[data-drag="${kind}"][data-id="${CSS.escape(id)}"]`);
      if (el) el.focus();
    }

    async _downloadBackup() {
      try {
        const data = await this._call({ type: "medication_tracker/export_data" });
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `medication-tracker-backup-${todayIso()}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        this._say(`Backup saved (${data.medications.length} medications)`);
      } catch (err) {
        this._say((err && err.message) || "Backup failed", true);
      }
    }

    async _restoreBackup(file) {
      let data;
      try {
        data = JSON.parse(await file.text());
      } catch (_err) {
        return this._say("That file is not a valid backup", true);
      }
      const count = Array.isArray(data.medications) ? data.medications.length : 0;
      if (!window.confirm(`Restore ${count} medication${count === 1 ? "" : "s"} from this backup? This replaces everything currently stored. A safety copy of the current data is saved first.`)) return;
      const result = await this._run({ type: "medication_tracker/import_data", data }, null);
      if (result) this._say(`Restored ${result.medications} medications and ${result.groups} groups`);
    }

    async _exportCsv() {
      try {
        const { logs } = await this._call({ type: "medication_tracker/get_history", days: 365 });
        const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
        const lines = [["When", "Person", "Medication", "Via", "Taken by"].map(cell).join(",")];
        for (const l of logs) {
          lines.push([l.taken_at, l.profile_name, l.medication_name, l.source, l.taken_by].map(cell).join(","));
        }
        const blob = new Blob([lines.join("\n")], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "medication-history.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        this._say(`Exported ${logs.length} doses`);
      } catch (err) {
        this._say((err && err.message) || "Export failed", true);
      }
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
        body = this._form
          ? this._renderForm()
          : this._gform
          ? this._renderGroupForm()
          : this._quick
          ? this._renderQuick()
          : this._renderMedications();
      } else if (this._tab === "history") {
        body = this._report ? this._renderReport() : this._renderHistory();
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
      const toast = `<div class="toastbox">${this._toastHtml()}</div>`;
      const scrollTop = this.scrollTop;
      root.innerHTML = `<style>${STYLE}</style>
        <div class="bar">${this._narrow ? '<button class="menu" data-action="menu" aria-label="Menu">☰</button>' : ""}<h1>Medications</h1><button class="iconbtn" data-action="toggle-large" aria-pressed="${this._large}" title="Bigger buttons for tablets and touch screens">${this._large ? "Aa −" : "Aa +"}</button></div>
        <div class="tabs">${tabs}</div>
        <main class="${this._large ? "large" : ""}">${body}</main>${toast}`;
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
      const byIdMed = Object.fromEntries(s.medications.map((m) => [m.medication_id, m]));
      const parts = [];
      for (const p of s.pauses || []) {
        parts.push(`<div class="banner">⏸ Reminders paused for <b>${esc(p.profile_name)}</b> ${p.active ? "until" : "from " + esc(p.start) + " to"} ${esc(p.end)}${
          this._isAdmin ? ` <button class="btn secondary" style="padding:4px 12px;margin-left:8px" data-action="resume" data-index="${p.index}">${p.active ? "Resume now" : "Cancel"}</button>` : ""
        }</div>`);
      }
      if (this._pauseForm) {
        const pf = this._pauseForm;
        const people = Object.entries(s.profiles || {});
        parts.push(`<div class="card"><h2>Pause reminders</h2>
          <div class="sub" style="margin-bottom:12px">Going away or ill? No reminders are sent and nothing counts as missed on the days you pick.</div>
          <div class="grid">
            <label class="field">Who<select data-pause="profile_id"><option value="">Everyone</option>${people.map(([id, n]) => `<option value="${esc(id)}" ${pf.profile_id === id ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
            <label class="field">From<input type="date" data-pause="start" value="${esc(pf.start)}"></label>
            <label class="field">Last day<input type="date" data-pause="end" value="${esc(pf.end)}"></label>
          </div>
          <div class="actions" style="margin-top:16px"><button class="btn big" data-action="pause-save">Pause</button><button class="btn secondary big" data-action="cancel">Cancel</button></div></div>`);
      }
      parts.push(`<div class="card hero"><div><h2 style="margin:0">${
        outstanding ? `${outstanding} to take now` : "Nothing due right now"
      }</h2><div class="sub">${s.summary.next_due ? "Next dose " + esc(fmtDateTime(s.summary.next_due)) : "No upcoming doses"}</div></div>${
        outstanding ? '<button class="btn big" data-action="take-all">✓ Take all due</button>' : ""
      }</div>`);
      if (this._isAdmin && !this._pauseForm) {
        parts.push(`<div class="noprint" style="text-align:right;margin:-8px 0 12px"><button class="btn secondary" style="padding:6px 14px" data-action="pause-open">⏸ Pause reminders</button></div>`);
      }
      if (needsRefill.length) {
        parts.push(`<div class="banner">Running low:${needsRefill
          .map(
            (m) => `<div class="mrow first" style="padding:4px 0"><div class="grow">${esc(m.medication_name)} <span class="sub">${esc(m.profile_name)} · ${esc(m.remaining_quantity)} left${m.days_remaining !== null && m.days_remaining !== undefined ? ` (~${esc(m.days_remaining)} days)` : ""}</span></div><button class="btn secondary" style="padding:4px 12px" data-action="refill" data-id="${esc(m.medication_id)}">Add stock</button></div>`
          )
          .join("")}</div>`);
      }
      const byProfile = {};
      for (const dose of doses) (byProfile[dose.profile_name] ||= { id: dose.profile_id, doses: [] }).doses.push(dose);
      const asNeeded = s.as_needed || [];
      if (!doses.length && !asNeeded.length) parts.push(`<div class="card empty">Nothing scheduled today.</div>`);
      if (asNeeded.length) {
        const rows = asNeeded
          .map((m) => {
            const count = m.max_doses_per_day ? `${m.doses_today} of ${m.max_doses_per_day} today` : `${m.doses_today} today`;
            const note = m.at_limit ? "Daily limit reached" : m.duplicate_dose_warning || "";
            return `<div class="row"><div class="grow"><div>${esc(m.medication_name)} <span class="sub">${esc(m.profile_name)}</span></div>
              <div class="sub">${esc(m.dosage)} · ${esc(count)}${note ? " · " + esc(note) : ""}</div></div>
              <div class="actions"><button class="btn" data-action="take" data-id="${esc(m.medication_id)}" ${m.at_limit ? "disabled" : ""}>Take</button>
              <button class="btn secondary" data-action="take-earlier" data-id="${esc(m.medication_id)}" ${m.at_limit ? "disabled" : ""}>Earlier…</button>
              ${m.doses_today ? `<button class="btn secondary" data-action="undo" data-id="${esc(m.medication_id)}">Undo</button>` : ""}</div></div>`;
          })
          .join("");
        parts.push(`<div class="card"><h2>As needed</h2>${rows}</div>`);
      }
      const doseRow = (d, inGroup) => {
        const cls = STATUS_CLASS[d.status] || "muted";
        const label = STATUS_LABEL[d.status] || d.status;
        const id = esc(d.medication_id);
        let actions = "";
        if (d.can_take) {
          actions = `<div class="actions"><button class="btn" data-action="take" data-id="${id}">Taken</button>
             <button class="btn secondary" data-action="take-earlier" data-id="${id}">Earlier…</button>
             ${inGroup ? "" : `<button class="btn secondary" data-action="snooze" data-id="${id}" data-minutes="10">Snooze 10m</button>`}
             <button class="btn secondary" data-action="skip" data-id="${id}">Skip</button></div>`;
        } else if (d.status === "Taken") {
          actions = `<div class="actions"><button class="btn secondary" data-action="undo" data-id="${id}">Undo</button></div>`;
        }
        return `<div class="row">${inGroup ? "" : `<span class="time">${esc(d.time)}</span>`}
          <div class="grow"><div>${esc(d.medication_name)}${
            byIdMed[d.medication_id] && byIdMed[d.medication_id].food_note ? ` <span class="tag">🍽 ${esc(FOOD[byIdMed[d.medication_id].food_note])}</span>` : ""
          }</div><div class="sub">${esc(d.dosage)}</div></div>
          <span class="chip ${cls}">${esc(label)}</span>${actions}</div>`;
      };
      for (const [name, group] of Object.entries(byProfile)) {
        const canTake = group.doses.filter((d) => d.can_take).length;
        // Doses of one group at one time sit together as a checklist.
        const blocks = [];
        for (const d of group.doses) {
          const key = d.group_id ? `${d.scheduled_at}|${d.group_id}` : null;
          const last = blocks[blocks.length - 1];
          if (key && last && last.key === key) last.doses.push(d);
          else blocks.push({ key, group_id: d.group_id, group_name: d.group_name, time: d.time, doses: [d] });
        }
        const rows = blocks
          .map((blk) => {
            if (!blk.key) return doseRow(blk.doses[0], false);
            const done = blk.doses.filter((d) => d.status === "Taken").length;
            const total = blk.doses.length;
            const ready = blk.doses.filter((d) => d.can_take);
            const pct = Math.round((done / total) * 100);
            const takeBtn = ready.length
              ? `<button class="btn" data-action="take-group" data-label="${esc(blk.group_name)}" data-ids="${esc(ready.map((d) => d.medication_id).join(","))}">✓ Take all${ready.length < total ? ` (${ready.length})` : ""}</button>`
              : "";
            const needs = blk.doses.some((d) => d.can_take || d.status === "Missed Dose");
            const key = `${blk.group_id}|${blk.time}`;
            const open = key in this._todayOpen ? this._todayOpen[key] : needs;
            return `<div class="block" data-block="${esc(blk.group_id)}">
              <div class="bhead"><button class="linkbtn" data-action="toggle-block" data-key="${esc(key)}" data-open="${open ? "1" : "0"}" aria-expanded="${open}"><span class="chev">${open ? "▾" : "▸"}</span><span class="time">${esc(blk.time)}</span><strong>${esc(blk.group_name)}</strong></button>
                <span class="sub">${done === total ? "✓ " : ""}${done} of ${total} taken</span><div class="bar2"><i style="width:${pct}%"></i></div>${takeBtn}</div>
              ${open ? blk.doses.map((d) => doseRow(d, true)).join("") : ""}</div>`;
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

    _medRow(m, first, dragOk = true) {
      const admin = this._isAdmin;
      const days = m.days_of_week && m.days_of_week.length ? m.days_of_week.map((d) => DAYS[d]).join(", ") : "Every day";
      const stock =
        m.remaining_quantity === null || m.remaining_quantity === undefined
          ? "Stock not tracked"
          : `${m.remaining_quantity} left${m.days_remaining !== null ? ` (~${m.days_remaining} days)` : ""}`;
      const when = m.as_needed
        ? `As needed${m.max_doses_per_day ? ` (max ${esc(m.max_doses_per_day)} per day)` : ""}`
        : m.group_id
        ? "⏰ with the group"
        : `⏰ ${esc((m.schedules || []).join(", "))} · ${esc(m.interval_days > 1 ? "every " + m.interval_days + " days" : days)}`;
      const handle =
        admin && !m.as_needed && dragOk
          ? `<button class="handle" data-drag="med" data-id="${esc(m.medication_id)}" aria-label="Move ${esc(m.medication_name)}. Drag, or use the up and down arrow keys to reorder" title="Drag to move">⠿</button>`
          : "";
      const conflicts = (m.conflicts || [])
        .map((c) => `<div class="warnline">⚠ Only ${esc(c.gap_minutes)} min from ${esc(c.medication_name)} (keep ${esc(c.required_minutes)} min apart)</div>`)
        .join("");
      return `<div class="mrow ${first ? "first" : ""}" data-row="med" data-id="${esc(m.medication_id)}" data-profile="${esc(m.profile_id)}" data-label="${esc(m.medication_name)} ${esc(m.dosage)}">
        ${handle}
        <div class="grow"><div>${esc(m.medication_name)} <span class="sub">${esc(m.dosage)}</span>${m.purpose ? ` <span class="sub">· ${esc(m.purpose)}</span>` : ""} ${m.needs_refill ? '<span class="chip warn">Refill needed</span>' : ""}${m.food_note ? ` <span class="tag">🍽 ${esc(FOOD[m.food_note])}</span>` : ""}${m.paused ? ' <span class="tag">⏸ paused</span>' : ""}</div>
          <div class="sub">${when}${m.end_date ? ` · ${m.course_ended ? "course ended" : "until"} ${esc(m.end_date)}` : ""}</div>
          <div class="sub">📦 ${esc(stock)}${m.nfc_tag_id ? " · 🏷 NFC tag set" : ""}${m.as_needed ? "" : ` · Adherence ${esc(m.compliance_percentage)}% · ${esc(m.missed_doses)} missed`}</div>
          <div class="sub">Next: ${esc(fmtDateTime(m.next_dose))} · Last taken: ${esc(fmtDateTime(m.last_taken))}${m.last_taken_by ? " by " + esc(m.last_taken_by) : ""}</div>${conflicts}</div>
        <div class="actions">
          <button class="btn secondary" data-action="refill" data-id="${esc(m.medication_id)}">Add stock</button>
          ${admin ? `<button class="btn secondary" data-action="edit" data-id="${esc(m.medication_id)}">Edit</button>
          <button class="btn secondary" data-action="duplicate" data-id="${esc(m.medication_id)}" title="Start a new medication from this one">Copy</button>
          <button class="btn danger" data-action="delete" data-id="${esc(m.medication_id)}">Delete</button>` : ""}
        </div></div>`;
    }

    _renderMedications() {
      const s = this._state;
      const admin = this._isAdmin;
      const hasGroups = (s.groups || []).length > 0;
      const header = `<div class="hero" style="margin-bottom:12px"><div class="sub">${s.medications.length} medication${
        s.medications.length === 1 ? "" : "s"
      }</div>${
        admin
          ? '<div class="actions"><button class="btn" data-action="add">+ Add medication</button><button class="btn secondary" data-action="quick-add">Quick add several</button><button class="btn secondary" data-action="new-group">+ New group</button></div>'
          : ""
      }</div>`;
      if (!s.medications.length && !hasGroups) {
        return (
          header +
          `<div class="card empty"><p>No medications yet.</p>${admin ? '<p class="sub">Taking several things at the same time, like vitamins? Use <b>Quick add several</b> to type them all in one go and get a single reminder.</p>' : ""}</div>`
        );
      }
      const tip =
        admin && (s.medications.length > 1 || hasGroups)
          ? `<div class="hint">Drag <b>⠿</b> to put medications into groups or change the order. A group gets one reminder and one tick-all button, but every medication is still tracked on its own.</div>`
          : "";
      const tools = `<div class="hero" style="margin-bottom:12px;gap:8px">
        <input class="search" style="flex:1;margin:0;min-width:160px" type="search" data-search placeholder="Search medications…" value="${esc(this._search)}" aria-label="Search medications">
        ${hasGroups ? '<div class="actions"><button class="btn secondary" data-action="collapse-all">Collapse groups</button><button class="btn secondary" data-action="expand-all">Expand groups</button></div>' : ""}</div>`;
      return header + tip + tools + `<div class="medlist">${this._medListHtml()}</div>`;
    }

    _medListHtml() {
      const s = this._state;
      const admin = this._isAdmin;
      const q = this._search.trim().toLowerCase();
      const hit = (m) =>
        !q || [m.medication_name, m.purpose, m.dosage].some((x) => (x || "").toLowerCase().includes(q));
      const dragOk = !q;
      const people = new Map();
      for (const m of s.medications) people.set(m.profile_id, m.profile_name);
      for (const g of s.groups || []) people.set(g.profile_id, g.profile_name);
      const sections = [...people.entries()]
        .sort((a, b) => a[1].localeCompare(b[1]))
        .map(([pid, name]) => {
          const meds = s.medications.filter((m) => m.profile_id === pid);
          const byId = Object.fromEntries(meds.map((m) => [m.medication_id, m]));
          const groups = (s.groups || []).filter((g) => g.profile_id === pid).sort((a, b) => a.order - b.order);
          const groupHtml = groups
            .map((g) => {
              const all = (g.member_ids || []).map((id) => byId[id]).filter(Boolean);
              const nameHit = q && g.name.toLowerCase().includes(q);
              const members = q && !nameHit ? all.filter(hit) : all;
              if (q && !nameHit && !members.length) return "";
              const folded = !q && this._collapsed.has(g.group_id);
              const days = g.days_of_week && g.days_of_week.length ? g.days_of_week.map((d) => DAYS[d]).join(", ") : "every day";
              const low = all.filter((m) => m.needs_refill).length;
              const conflicts = all.reduce((n, m) => n + (m.conflicts || []).length, 0);
              const handle = admin && dragOk
                ? `<button class="handle" data-drag="group" data-id="${esc(g.group_id)}" aria-label="Move group ${esc(g.name)}. Drag, or use the up and down arrow keys to reorder" title="Drag to reorder">⠿</button>`
                : "";
              return `<div class="gcard" data-row="group" data-id="${esc(g.group_id)}" data-profile="${esc(pid)}" data-label="${esc(g.name)}">
                <div class="mrow first" style="padding-top:0">${handle}
                  <button class="linkbtn grow" data-action="toggle-group" data-id="${esc(g.group_id)}" aria-expanded="${!folded}"><span class="chev">${folded ? "▸" : "▾"}</span><span><strong>${esc(g.name)}</strong> <span class="sub">⏰ ${esc(g.schedules.join(", "))} · ${esc(g.interval_days > 1 ? "every " + g.interval_days + " days" : days)} · ${all.length} item${all.length === 1 ? "" : "s"}${g.notification_enabled ? "" : " · reminders off"}${g.nfc_tag_id ? " · 🏷 tag" : ""}${low ? ` · ${low} low` : ""}${conflicts ? " · ⚠" : ""}</span></span></button>
                  ${admin ? `<button class="btn secondary" data-action="edit-group" data-id="${esc(g.group_id)}">Edit group</button>` : ""}</div>
                <div class="zone ${folded ? "collapsed" : ""}" data-zone="${esc(g.group_id)}" data-profile="${esc(pid)}"><div class="zonebody">${
                  members.length ? members.map((m, i) => this._medRow(m, i === 0, dragOk)).join("") : '<div class="emptyhint">Drag medications here</div>'
                }</div></div></div>`;
            })
            .join("");
          const loose = meds
            .filter((m) => !m.group_id && !m.as_needed && hit(m))
            .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.medication_name.localeCompare(b.medication_name));
          const prn = meds.filter((m) => m.as_needed && hit(m));
          const showZone = loose.length || (groups.length && !q);
          if (q && !groupHtml && !loose.length && !prn.length) return "";
          return `<div class="card"><h2>${esc(name)}</h2>
            ${groupHtml ? `<div data-grouplist data-profile="${esc(pid)}">${groupHtml}</div>` : ""}
            ${
              showZone
                ? `${groups.length ? '<div class="sub" style="margin:4px 0">Own reminder (not in a group)</div>' : ""}<div class="zone ungrouped" data-zone="" data-profile="${esc(pid)}"><div class="zonebody">${
                    loose.length ? loose.map((m, i) => this._medRow(m, i === 0, dragOk)).join("") : '<div class="emptyhint">Drag here to take a medication out of its group</div>'
                  }</div></div>`
                : ""
            }
            ${prn.length ? `<div class="sub" style="margin:12px 0 4px">As needed</div>${prn.map((m, i) => this._medRow(m, i === 0, dragOk)).join("")}` : ""}
          </div>`;
        })
        .join("");
      return sections || `<div class="card empty">Nothing matches "${esc(this._search)}".</div>`;
    }

    _apartListHtml() {
      const f = this._form;
      const pid = this._profileIdByName(f.profile_name);
      const others = this._state.medications.filter(
        (m) => m.profile_id === pid && m.medication_id !== f.medication_id && !m.as_needed
      );
      if (!others.length) return '<div class="sub">No other medications for this person yet.</div>';
      return others
        .map(
          (m) => `<label><input type="checkbox" data-apart="${esc(m.medication_id)}" ${f.keep_apart.includes(m.medication_id) ? "checked" : ""}> ${esc(m.medication_name)}</label>`
        )
        .join("");
    }

    _groupOptions(groups, selected, blankLabel) {
      return (
        `<option value="">${esc(blankLabel)}</option>` +
        groups.map((g) => `<option value="${esc(g.group_id)}" ${g.group_id === selected ? "selected" : ""}>${esc(g.name)} (${esc(g.schedules.join(", "))})</option>`).join("")
      );
    }

    _quickGroupOptions(groups, selected) {
      return (
        `<option value="new" ${selected === "new" ? "selected" : ""}>A new group…</option>` +
        groups.map((g) => `<option value="${esc(g.group_id)}" ${g.group_id === selected ? "selected" : ""}>${esc(g.name)} (${esc(g.schedules.join(", "))})</option>`).join("") +
        `<option value="" ${selected === "" ? "selected" : ""}>No group (each gets its own reminder)</option>`
      );
    }

    _memberListHtml() {
      const f = this._gform;
      const pid = this._profileIdByName(f.profile_name);
      const meds = this._state.medications.filter((m) => m.profile_id === pid && !m.as_needed);
      if (!meds.length) return '<div class="sub">No medications for this person yet. Add some first, or use Quick add.</div>';
      return meds
        .map((m) => {
          const other = m.group_id && m.group_id !== f.group_id ? (this._state.groups || []).find((g) => g.group_id === m.group_id) : null;
          return `<label><input type="checkbox" data-member="${esc(m.medication_id)}" ${f.member_ids.includes(m.medication_id) ? "checked" : ""}> ${esc(m.medication_name)} <span class="sub">${esc(m.dosage)}${other ? ` · currently in ${esc(other.name)}` : ""}</span></label>`;
        })
        .join("");
    }

    _timesAndDays(f) {
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
      return `<div class="times">${times}<button class="btn secondary" data-action="add-time">+ Add time</button></div>
        <div class="days" style="margin-top:12px">${days}</div>`;
    }

    _renderGroupForm() {
      const f = this._gform;
      const editing = !!f.group_id;
      const profiles = Object.values(this._state.profiles || {});
      const defaultNotify = this._state.settings.default_notify_service;
      const scanning = this._scan ? `<div class="banner">Hold your phone to the NFC tag now… <button class="btn secondary" data-action="stop-scan">Cancel</button></div>` : "";
      return `<div class="card"><h2>${editing ? "Edit group" : "New group"}</h2>
        <div class="sub" style="margin-bottom:12px">Everything in a group is reminded together in one notification, with one button to tick it all off. Each medication is still tracked individually.</div>
        <datalist id="profiles">${profiles.map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
        <div class="grid">
          <label class="field">Group name<input data-field="name" value="${esc(f.name)}" placeholder="e.g. Morning vitamins"></label>
          <label class="field">Who is it for?<input data-field="profile_name" value="${esc(f.profile_name)}" list="profiles" placeholder="e.g. Mike"></label>
        </div>
        <h2 style="margin-top:16px">When</h2>
        ${this._timesAndDays(f)}
        <div class="grid" style="margin-top:12px">
          <label class="field">Repeat every N days (1 = daily)<input type="number" min="1" max="30" data-field="interval_days" value="${esc(f.interval_days)}"></label>
          <label class="field">First day (only for every-N-days)<input type="date" data-field="anchor_date" value="${esc(f.anchor_date)}"></label>
        </div>
        <h2 style="margin-top:16px">What's in it</h2>
        <div class="memberlist">${this._memberListHtml()}</div>
        <h2 style="margin-top:16px">Taking it</h2>
        ${scanning}
        <div class="grid">
          <label class="field">NFC tag ID (optional, ticks the whole group)<span style="display:flex;gap:6px"><input style="flex:1" data-field="nfc_tag_id" value="${esc(f.nfc_tag_id)}" placeholder="scan or paste"><button class="btn secondary" data-action="scan-form" type="button">Scan</button></span></label>
          <label class="field">Phone to notify<select data-field="notify_service">${this._notifyOptions(f.notify_service, defaultNotify ? `Use default (${defaultNotify})` : "Use default (set in Settings)")}</select></label>
        </div>
        <label class="field" style="margin-top:12px;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" data-field="notification_enabled" ${f.notification_enabled ? "checked" : ""}> Send reminders</label>
        <div class="actions" style="margin-top:20px">
          <button class="btn big" data-action="save-group">Save group</button>
          <button class="btn secondary big" data-action="cancel">Cancel</button>
          ${editing ? `<button class="btn danger" data-action="delete-group" data-id="${esc(f.group_id)}">Delete group</button>` : ""}
        </div></div>`;
    }

    _renderQuick() {
      const f = this._quick;
      const profiles = Object.values(this._state.profiles || {});
      const groups = this._groupsFor(f.profile_name);
      const needsTimes = f.group_choice === "new" || f.group_choice === "";
      const times = f.schedules
        .map(
          (t, i) => `<span><input type="time" value="${esc(t)}" data-time="${i}">${
            f.schedules.length > 1 ? `<button class="btn danger" style="padding:4px 10px" data-action="remove-time" data-index="${i}" aria-label="Remove time">×</button>` : ""
          }</span>`
        )
        .join("");
      return `<div class="card"><h2>Quick add several</h2>
        <div class="sub" style="margin-bottom:12px">Type one medication or supplement per line. Add the dose after a comma if you like, for example <code>Vitamin D, 1000 IU</code>.</div>
        <datalist id="profiles">${profiles.map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
        <div class="grid">
          <label class="field">Who are they for?<input data-field="profile_name" value="${esc(f.profile_name)}" list="profiles" placeholder="e.g. Mike"></label>
          <label class="field">Put them in<select data-field="group_choice">${this._quickGroupOptions(groups, f.group_choice)}</select></label>
          ${f.group_choice === "new" ? `<label class="field">New group name<input data-field="new_name" value="${esc(f.new_name)}" placeholder="e.g. Morning vitamins"></label>` : ""}
        </div>
        ${needsTimes ? `<h2 style="margin-top:16px">At what time${f.group_choice === "" ? " (each gets its own reminder)" : ""}?</h2><div class="times">${times}<button class="btn secondary" data-action="add-time">+ Add time</button></div>` : ""}
        <div class="sub" style="margin-top:16px">Starting points (tap to add, then edit the doses from your labels):</div>
        <div class="actions" style="margin-top:6px">${TEMPLATES.map((t, i) => `<button class="btn secondary" type="button" data-action="template" data-index="${i}">${esc(t[0])}</button>`).join("")}</div>
        <label class="field" style="margin-top:12px">Medications<textarea data-field="text" placeholder="Vitamin D, 1000 IU&#10;Magnesium, 200 mg&#10;Zinc&#10;Omega 3, 2 capsules">${esc(f.text)}</textarea></label>
        <div class="actions" style="margin-top:20px">
          <button class="btn big" data-action="save-quick">Add them</button>
          <button class="btn secondary big" data-action="cancel">Cancel</button>
        </div></div>`;
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
          ${
            f.as_needed
              ? ""
              : `<label class="field">Group (shares one reminder)<select data-field="group_id">${this._groupOptions(this._groupsFor(f.profile_name), f.group_id, "No group")}</select></label>`
          }
        </div>
        <h2 style="margin-top:16px">When</h2>
        <label class="field" style="flex-direction:row;align-items:center;gap:8px;margin-bottom:8px"><input type="checkbox" data-field="as_needed" ${f.as_needed ? "checked" : ""}> As needed (no fixed times, e.g. paracetamol)</label>
        ${
          f.as_needed
            ? `<div class="grid">${field("max_doses_per_day", "Most doses per day (blank = no limit)", 'type="number" min="0" max="48"')}</div>`
            : f.group_id
            ? `<div class="hint">This medication uses the times of its group, so it is reminded together with the others. Choose "No group" above to give it its own times.</div>`
            : `<div class="times">${times}<button class="btn secondary" data-action="add-time">+ Add time</button></div>
        <div class="days" style="margin-top:12px">${days}</div>
        <div class="grid" style="margin-top:12px">
          ${field("interval_days", "Repeat every N days (1 = daily)", 'type="number" min="1" max="30"')}
          <label class="field">First day (only for every-N-days)<input type="date" data-field="anchor_date" value="${esc(f.anchor_date)}"></label>
        </div>`
        }
        <div class="grid" style="margin-top:12px"><label class="field">Course ends (optional)<input type="date" data-field="end_date" value="${esc(f.end_date)}"></label></div>
        <h2 style="margin-top:16px">Food and timing</h2>
        <div class="grid">
          <label class="field">Food<select data-field="food_note"><option value="">No instruction</option><option value="with_food" ${f.food_note === "with_food" ? "selected" : ""}>Take with food</option><option value="empty_stomach" ${f.food_note === "empty_stomach" ? "selected" : ""}>Take on an empty stomach</option></select></label>
          ${field("keep_apart_minutes", "Keep apart by (minutes)", 'type="number" min="15" max="720"')}
        </div>
        <div class="sub" style="margin:10px 0 2px">Keep apart from (for example iron and calcium):</div>
        <div class="memberlist apartlist">${this._apartListHtml()}</div>
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
            ${field("escalate_after_minutes", "Tell caregiver if not taken after (min, 0 = off)", 'type="number" min="0" max="1440"')}
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
      const admin = this._isAdmin;
      const scheduled = this._state.medications.filter((m) => !m.as_needed);
      const adherence = scheduled.length
        ? `<div class="card"><h2>Adherence</h2><table><tr><th>Medication</th><th>Who</th><th>Taken on schedule</th><th>Missed</th></tr>${scheduled
            .map(
              (m) => `<tr><td>${esc(m.medication_name)}</td><td>${esc(m.profile_name)}</td><td>${esc(m.compliance_percentage)}%</td><td>${esc(m.missed_doses)}</td></tr>`
            )
            .join("")}</table></div>`
        : "";
      if (!logs.length) return adherence + `<div class="card empty">No doses logged yet.</div>`;
      const rows = logs
        .map(
          (l) => `<tr><td>${esc(fmtDateTime(l.taken_at))}</td><td>${esc(l.profile_name)}</td><td>${esc(l.medication_name)}</td>
            <td class="hide-narrow">${esc(l.source)}${l.taken_by ? " · " + esc(l.taken_by) : ""}</td>
            <td>${admin ? `<button class="btn danger" style="padding:4px 10px" data-action="delete-dose" data-id="${esc(l.medication_id)}" data-taken-at="${esc(l.taken_at)}">Delete</button>` : ""}</td></tr>`
        )
        .join("");
      return `${adherence}<div class="card"><div class="hero"><h2>Recent doses</h2><div class="actions"><button class="btn secondary" data-action="report-open">Print report</button><button class="btn secondary" data-action="export-csv">Export CSV</button></div></div><table><tr><th>When</th><th>Who</th><th>Medication</th><th class="hide-narrow">Via / by</th><th></th></tr>${rows}</table></div>`;
    }

    _renderReport() {
      const s = this._state;
      const groupName = Object.fromEntries((s.groups || []).map((g) => [g.group_id, g.name]));
      const people = new Map();
      for (const m of s.medications) people.set(m.profile_id, m.profile_name);
      const today = new Date().toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" });
      const body = [...people.entries()]
        .sort((a, b) => a[1].localeCompare(b[1]))
        .map(([pid, name]) => {
          const rows = s.medications
            .filter((m) => m.profile_id === pid)
            .sort((a, b) => a.medication_name.localeCompare(b.medication_name))
            .map((m) => {
              const days = m.days_of_week && m.days_of_week.length ? m.days_of_week.map((d) => DAYS[d]).join(" ") : "daily";
              const when = m.as_needed ? "As needed" : `${(m.schedules || []).join(", ")} (${m.interval_days > 1 ? "every " + m.interval_days + " days" : days})`;
              const extra = [m.food_note ? FOOD[m.food_note] : "", m.purpose, m.instructions, m.end_date ? "until " + m.end_date : ""].filter(Boolean).join("; ");
              return `<tr><td>${esc(m.medication_name)}</td><td>${esc(m.dosage)}</td><td>${esc(when)}</td><td>${esc(groupName[m.group_id] || "")}</td><td>${esc(extra)}</td><td>${m.as_needed ? "-" : esc(m.compliance_percentage) + "%"}</td><td>${m.as_needed ? "-" : esc(m.missed_doses)}</td></tr>`;
            })
            .join("");
          return `<h3>${esc(name)}</h3><table><tr><th>Medication</th><th>Dose</th><th>When</th><th>Group</th><th>Notes</th><th>Taken on schedule</th><th>Missed</th></tr>${rows}</table>`;
        })
        .join("");
      return `<div class="noprint actions" style="margin-bottom:12px"><button class="btn" data-action="print">Print or save as PDF</button><button class="btn secondary" data-action="report-close">Back</button></div>
        <div class="card report"><h2>Medication report</h2><div class="sub">Prepared ${esc(today)}. Adherence counts doses taken on schedule over the stored history.</div>${body || "<p>No medications.</p>"}</div>`;
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
        <div class="card"><h2>Reminders</h2>
          <label class="field" style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" data-setting="critical_notifications" ${d.critical_notifications !== false ? "checked" : ""} ${admin ? "" : "disabled"}> Loud alarm-style notifications for due, missed and escalated doses (Android)</label>
          <div class="grid" style="margin-top:12px">
            <label class="field">Tell this phone when a dose is overdue<select data-setting="escalation_notify_service" ${admin ? "" : "disabled"}>${this._notifyOptions(d.escalation_notify_service, "Nobody")}</select></label>
            <label class="field">Speak reminders on (e.g. an Alexa notify service)<select data-setting="announce_service" ${admin ? "" : "disabled"}>${this._notifyOptions(d.announce_service, "Don't announce")}</select></label>
            <label class="field">Only announce when this person is home<input data-setting="announce_only_when_home_entity" value="${esc(d.announce_only_when_home_entity || "")}" placeholder="person.mike" ${admin ? "" : "disabled"}></label>
            <label class="field">Quiet hours start<input type="time" data-setting="quiet_hours_start" value="${esc(d.quiet_hours_start || "")}" ${admin ? "" : "disabled"}></label>
            <label class="field">Quiet hours end<input type="time" data-setting="quiet_hours_end" value="${esc(d.quiet_hours_end || "")}" ${admin ? "" : "disabled"}></label>
          </div>
          <div class="sub" style="margin-top:8px">Quiet hours silence announcements and refill reminders. Dose reminders to your phone are never silenced.</div>
        </div>
        <div class="card"><h2>People and weekly summary</h2>
          <div class="sub" style="margin-bottom:12px">Send each person's reminders to their own phone. A medication or group's own phone still wins.</div>
          ${
            Object.keys(profiles).length
              ? `<div class="grid">${Object.entries(profiles)
                  .map(
                    ([pid, name]) => `<label class="field">${esc(name)}'s phone<select data-profile-phone="${esc(pid)}" ${admin ? "" : "disabled"}>${this._notifyOptions(
                      (d.profile_notify_services || {})[pid],
                      "Use the default phone"
                    )}</select></label>`
                  )
                  .join("")}</div>`
              : '<div class="sub">Add a medication first.</div>'
          }
          <h2 style="margin-top:16px;font-size:14px">Weekly summary</h2>
          <div class="grid">
            <label class="field">Send it to<select data-setting="weekly_summary_service" ${admin ? "" : "disabled"}>${this._notifyOptions(d.weekly_summary_service, "Don't send")}</select></label>
            <label class="field">On<select data-setting="weekly_summary_day" ${admin ? "" : "disabled"}>${["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
              (label, i) => `<option value="${i}" ${Number(d.weekly_summary_day ?? 6) === i ? "selected" : ""}>${label} at 09:00</option>`
            ).join("")}</select></label>
          </div>
        </div>
        ${
          admin
            ? `<div class="card"><h2>Backup</h2>
          <div class="sub" style="margin-bottom:12px">A copy of everything (medications, history, groups and settings) is also saved automatically every day to the <code>medication_tracker_backups</code> folder in your Home Assistant config folder, and the last 14 are kept.</div>
          <div class="actions"><button class="btn secondary" data-action="backup-download">Download a backup</button><button class="btn secondary" data-action="backup-restore">Restore from a file…</button></div>
          <input type="file" accept="application/json,.json" data-restore hidden></div>`
            : ""
        }
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
