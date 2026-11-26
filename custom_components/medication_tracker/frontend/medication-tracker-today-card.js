/* Medication Tracker "Today" dashboard card. Plain web component, no build step.
 *
 *   type: custom:medication-tracker-today-card
 *   title: Medications        # optional
 *   profile: mike             # optional: only show this person (profile id)
 */
(() => {
  if (customElements.get("medication-tracker-today-card")) return;

  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CLASS = { Taken: "ok", "Due Now": "warn", Snoozed: "warn", "Missed Dose": "bad", Skipped: "muted", "On Track": "muted" };
  const LABEL = { "On Track": "Upcoming", "Due Now": "Due now", "Missed Dose": "Missed" };

  class MedicationTrackerTodayCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._state = null;
      this._busy = false;
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    }

    static getStubConfig() {
      return { title: "Medications" };
    }

    setConfig(config) {
      this._config = config || {};
      this._render();
    }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) this._load();
    }

    getCardSize() {
      return 4;
    }

    connectedCallback() {
      if (!this._timer) this._timer = setInterval(() => this._load(), 30000);
      if (this._hass) this._load();
    }

    disconnectedCallback() {
      clearInterval(this._timer);
      this._timer = null;
    }

    async _load() {
      if (!this._hass) return;
      try {
        this._state = await this._hass.callWS({ type: "medication_tracker/get_state" });
        this._error = null;
      } catch (err) {
        this._error = (err && err.message) || "Medication Tracker is not available";
      }
      this._render();
    }

    async _onClick(event) {
      const target = event.target.closest("[data-action]");
      if (!target || this._busy) return;
      const { action, id, profile } = target.dataset;
      const msg =
        action === "take"
          ? { type: "medication_tracker/take", medication_id: id }
          : action === "take-all"
            ? { type: "medication_tracker/take_all", ...(profile ? { profile_id: profile } : {}) }
            : null;
      if (!msg) return;
      this._busy = true;
      try {
        await this._hass.callWS(msg);
      } catch (err) {
        this._error = (err && err.message) || "Could not log the dose";
      } finally {
        this._busy = false;
      }
      this._load();
    }

    _render() {
      const cfg = this._config;
      const s = this._state;
      const only = (item) => !cfg.profile || item.profile_id === cfg.profile;
      let body;
      if (!s) {
        body = `<div class="msg">${esc(this._error || "Loading…")}</div>`;
      } else {
        const doses = (s.today || []).filter(only);
        const asNeeded = (s.as_needed || []).filter(only);
        const due = doses.filter((d) => d.can_take).length;
        const rows = doses
          .map(
            (d) => `<div class="row"><span class="time">${esc(d.time)}</span>
              <div class="grow">${esc(d.medication_name)}<div class="sub">${esc(d.profile_name)} · ${esc(d.dosage)}</div></div>
              ${
                d.can_take
                  ? `<button data-action="take" data-id="${esc(d.medication_id)}">Taken</button>`
                  : `<span class="chip ${CLASS[d.status] || "muted"}">${esc(LABEL[d.status] || d.status)}</span>`
              }</div>`
          )
          .join("");
        const prn = asNeeded
          .map((m) => {
            const count = m.max_doses_per_day ? `${m.doses_today}/${m.max_doses_per_day} today` : `${m.doses_today} today`;
            return `<div class="row"><div class="grow">${esc(m.medication_name)}<div class="sub">As needed · ${esc(count)}</div></div>
              <button data-action="take" data-id="${esc(m.medication_id)}" ${m.at_limit ? "disabled" : ""}>Take</button></div>`;
          })
          .join("");
        body = `${due > 1 ? `<button class="all" data-action="take-all" ${cfg.profile ? `data-profile="${esc(cfg.profile)}"` : ""}>✓ Take all due (${due})</button>` : ""}
          ${rows || ""}${prn}
          ${!rows && !prn ? '<div class="msg">Nothing scheduled today.</div>' : ""}
          ${this._error ? `<div class="msg err">${esc(this._error)}</div>` : ""}`;
      }
      this.shadowRoot.innerHTML = `<style>
        ha-card { padding:16px; }
        h2 { margin:0 0 8px; font-size:18px; font-weight:500; color:var(--primary-text-color); }
        .row { display:flex; align-items:center; gap:12px; padding:8px 0; border-top:1px solid var(--divider-color); color:var(--primary-text-color); }
        .row:first-of-type { border-top:0; }
        .time { font-variant-numeric:tabular-nums; font-weight:600; min-width:46px; }
        .grow { flex:1; min-width:0; } .sub { color:var(--secondary-text-color); font-size:12px; }
        button { font:inherit; font-size:14px; border:0; border-radius:16px; padding:6px 14px; cursor:pointer; background:var(--primary-color); color:var(--text-primary-color,#fff); }
        button[disabled] { opacity:.5; cursor:default; }
        button.all { width:100%; padding:10px; margin:4px 0 8px; font-size:15px; }
        .chip { font-size:12px; padding:3px 10px; border-radius:12px; }
        .chip.ok { background:rgba(67,160,71,.18); color:#2e7d32; } .chip.warn { background:rgba(255,160,0,.2); color:#b26a00; }
        .chip.bad { background:rgba(229,57,53,.18); color:#c62828; } .chip.muted { background:var(--divider-color); color:var(--secondary-text-color); }
        .msg { color:var(--secondary-text-color); padding:8px 0; } .err { color:var(--error-color,#c62828); }
      </style>
      <ha-card><h2>${esc(cfg.title || "Medications")}</h2>${body}</ha-card>`;
    }
  }

  customElements.define("medication-tracker-today-card", MedicationTrackerTodayCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "medication-tracker-today-card",
    name: "Medication Tracker - Today",
    description: "Today's doses with Taken and Take all due buttons.",
  });
})();
