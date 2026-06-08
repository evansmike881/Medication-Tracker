const DEFAULT_CONFIG = {
  type: "custom:medication-tracker-card",
  entity: "sensor.medication_tracker_medication_registry",
  title: "Medication Registry",
  show_header: true,
  show_summary: true,
  show_status_chip: true,
  show_profile_name: true,
  show_dosage: true,
  show_purpose: true,
  show_next_dose: true,
  show_last_taken: true,
  show_caregiver: true,
  show_schedule: true,
  show_compliance: true,
  show_actions: true,
  show_summary_medications: true,
  show_summary_due_now: true,
  show_summary_missed: true,
  show_summary_refill: true,
  compact_rows: false,
  max_rows: 0,
};

class MedicationTrackerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("medication-tracker-card-editor");
  }

  static getStubConfig() {
    return { ...DEFAULT_CONFIG };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }

    this._config = {
      ...DEFAULT_CONFIG,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._card) {
      this._renderCard();
    }
    this._update();
  }

  getCardSize() {
    return this._config?.compact_rows ? 6 : 8;
  }

  _renderCard() {
    const card = document.createElement("ha-card");
    card.className = "medication-tracker-card";
    card.innerHTML = `
      <style>
        .wrap {
          padding: 18px;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 16px;
        }
        .title {
          font-size: 1.35rem;
          font-weight: 700;
          letter-spacing: -0.02em;
        }
        .summary {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 10px;
          margin-bottom: 18px;
        }
        .summary.hidden,
        .header.hidden {
          display: none;
        }
        .summary-tile {
          border-radius: 16px;
          padding: 12px 14px;
          background:
            linear-gradient(180deg, rgba(var(--rgb-primary-color), 0.10), rgba(var(--rgb-primary-color), 0.04)),
            var(--ha-card-background, var(--card-background-color));
          border: 1px solid rgba(var(--rgb-primary-color), 0.12);
        }
        .summary-label {
          font-size: 0.8rem;
          opacity: 0.74;
          margin-bottom: 4px;
        }
        .summary-value {
          font-size: 1.2rem;
          font-weight: 700;
        }
        .table {
          display: grid;
          gap: 10px;
        }
        .row {
          border: 1px solid var(--divider-color);
          border-radius: 18px;
          padding: 14px;
          background: rgba(var(--rgb-primary-text-color), 0.02);
        }
        .row.compact {
          padding: 12px;
        }
        .row-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 10px;
        }
        .row.compact .row-top {
          margin-bottom: 8px;
        }
        .name {
          font-size: 1.04rem;
          font-weight: 700;
          line-height: 1.2;
        }
        .meta {
          opacity: 0.72;
          font-size: 0.9rem;
          margin-top: 2px;
        }
        .chip {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 0.75rem;
          font-weight: 700;
          white-space: nowrap;
        }
        .chip.on-track {
          background: rgba(46, 125, 50, 0.14);
          color: #2e7d32;
        }
        .chip.due-now {
          background: rgba(239, 108, 0, 0.16);
          color: #ef6c00;
        }
        .chip.missed-dose {
          background: rgba(198, 40, 40, 0.15);
          color: #c62828;
        }
        .chip.needs-refill {
          background: rgba(106, 27, 154, 0.14);
          color: #6a1b9a;
        }
        .details {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 10px;
          margin-bottom: 12px;
        }
        .row.compact .details {
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 8px;
          margin-bottom: 10px;
        }
        .detail {
          background: rgba(var(--rgb-primary-text-color), 0.03);
          border-radius: 14px;
          padding: 10px 12px;
        }
        .detail-label {
          font-size: 0.75rem;
          opacity: 0.68;
          margin-bottom: 3px;
        }
        .detail-value {
          font-size: 0.95rem;
          font-weight: 600;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .action {
          border: 0;
          border-radius: 12px;
          padding: 10px 12px;
          font: inherit;
          cursor: pointer;
          background: var(--primary-color);
          color: var(--text-primary-color);
          font-weight: 700;
        }
        .action.secondary {
          background: rgba(var(--rgb-primary-text-color), 0.07);
          color: var(--primary-text-color);
        }
        .empty {
          padding: 14px;
          border-radius: 16px;
          background: rgba(var(--rgb-primary-text-color), 0.03);
          opacity: 0.72;
        }
      </style>
      <div class="wrap">
        <div class="header" id="header"></div>
        <div class="summary" id="summary"></div>
        <div class="table" id="table"></div>
      </div>
    `;

    this._card = card;
    this._header = card.querySelector("#header");
    this._summary = card.querySelector("#summary");
    this._table = card.querySelector("#table");
    this.appendChild(card);
  }

  _update() {
    const entity = this._hass.states[this._config.entity];
    this._header.classList.toggle("hidden", !this._config.show_header);
    this._summary.classList.toggle("hidden", !this._config.show_summary);

    if (!entity) {
      this._header.innerHTML = `<div class="title">${this._config.title}</div>`;
      this._summary.innerHTML = "";
      this._table.innerHTML = `<div class="empty">Entity not found: ${this._config.entity}</div>`;
      return;
    }

    let rows = entity.attributes.rows || [];
    if (Number(this._config.max_rows) > 0) {
      rows = rows.slice(0, Number(this._config.max_rows));
    }

    this._header.innerHTML = this._config.show_header
      ? `<div class="title">${this._config.title}</div><div class="meta">${rows.length} tracked</div>`
      : "";

    const summaryTiles = [];
    if (this._config.show_summary_medications) {
      summaryTiles.push(["Medications", this._safeState("sensor.medication_tracker_medication_count")]);
    }
    if (this._config.show_summary_due_now) {
      summaryTiles.push(["Due Now", this._safeState("sensor.medication_tracker_due_now_count")]);
    }
    if (this._config.show_summary_missed) {
      summaryTiles.push(["Missed", this._safeState("sensor.medication_tracker_missed_dose_count")]);
    }
    if (this._config.show_summary_refill) {
      summaryTiles.push(["Refill", this._safeState("sensor.medication_tracker_refill_needed_count")]);
    }

    this._summary.innerHTML =
      this._config.show_summary && summaryTiles.length
        ? summaryTiles
            .map(
              ([label, value]) => `
                <div class="summary-tile">
                  <div class="summary-label">${label}</div>
                  <div class="summary-value">${value}</div>
                </div>
              `
            )
            .join("")
        : "";

    if (!rows.length) {
      this._table.innerHTML = `<div class="empty">No medications are currently tracked.</div>`;
      return;
    }

    this._table.innerHTML = rows
      .map((row) => {
        const statusClass = (row.status || "On Track").toLowerCase().replace(/\s+/g, "-");
        const details = [];
        const metaParts = [];

        if (this._config.show_profile_name && row.profile_name) {
          metaParts.push(row.profile_name);
        }
        if (this._config.show_dosage) {
          metaParts.push(row.dosage || "Dose not set");
        }

        if (this._config.show_purpose) {
          details.push(this._detail("Purpose", row.purpose || "Not set"));
        }
        if (this._config.show_next_dose) {
          details.push(this._detail("Next dose", this._formatDate(row.next_dose, "Not scheduled")));
        }
        if (this._config.show_last_taken) {
          details.push(this._detail("Last taken", this._formatDate(row.last_taken, "Not logged")));
        }
        if (this._config.show_caregiver) {
          details.push(this._detail("Caregiver", row.caregiver_name || "Not assigned"));
        }
        if (this._config.show_schedule) {
          details.push(this._detail("Schedule", (row.schedules || []).join(", ") || "None"));
        }
        if (this._config.show_compliance) {
          details.push(this._detail("Compliance", `${row.compliance_percentage ?? "0"}%`));
        }

        return `
          <div class="row ${this._config.compact_rows ? "compact" : ""}">
            <div class="row-top">
              <div>
                <div class="name">${row.medication_name}</div>
                ${metaParts.length ? `<div class="meta">${metaParts.join(" | ")}</div>` : ""}
              </div>
              ${this._config.show_status_chip ? `<div class="chip ${statusClass}">${row.status}</div>` : ""}
            </div>
            ${details.length ? `<div class="details">${details.join("")}</div>` : ""}
            ${
              this._config.show_actions
                ? `
                  <div class="actions">
                    <button class="action" data-action="log" data-entity="${row.button_entity_id}">
                      Log Dose
                    </button>
                    <button class="action secondary" data-action="more-info" data-entity="${row.next_dose_entity_id}">
                      Next Dose
                    </button>
                    <button class="action secondary" data-action="more-info" data-entity="${row.due_now_entity_id}">
                      Status
                    </button>
                  </div>
                `
                : ""
            }
          </div>
        `;
      })
      .join("");

    this._table.querySelectorAll("button[data-action]").forEach((button) => {
      button.onclick = () => this._handleAction(button.dataset.action, button.dataset.entity);
    });
  }

  _detail(label, value) {
    return `
      <div class="detail">
        <div class="detail-label">${label}</div>
        <div class="detail-value">${value}</div>
      </div>
    `;
  }

  async _handleAction(action, entityId) {
    if (!entityId) {
      return;
    }
    if (action === "log") {
      await this._hass.callService("button", "press", { entity_id: entityId });
      return;
    }
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId },
      })
    );
  }

  _formatDate(value, fallback) {
    if (!value) {
      return fallback;
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return fallback;
    }
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  _safeState(entityId) {
    return this._hass.states[entityId]?.state ?? "0";
  }
}

class MedicationTrackerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      ...DEFAULT_CONFIG,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._config) {
      return;
    }

    const entityOptions = this._entityOptions();
    this.innerHTML = `
      <style>
        .editor {
          display: grid;
          gap: 16px;
          padding: 8px 0 0;
        }
        .section {
          border: 1px solid var(--divider-color);
          border-radius: 16px;
          padding: 14px;
        }
        .section-title {
          font-size: 1rem;
          font-weight: 700;
          margin-bottom: 6px;
        }
        .section-copy {
          font-size: 0.85rem;
          opacity: 0.72;
          margin-bottom: 12px;
        }
        .field {
          display: grid;
          gap: 6px;
          margin-bottom: 12px;
        }
        .field:last-child {
          margin-bottom: 0;
        }
        .label {
          font-size: 0.9rem;
          font-weight: 600;
        }
        .hint {
          font-size: 0.8rem;
          opacity: 0.72;
        }
        input[type="text"],
        input[type="number"],
        select {
          width: 100%;
          box-sizing: border-box;
          border-radius: 10px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          padding: 10px 12px;
          font: inherit;
        }
        .toggle-grid {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        }
        .toggle {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          border-radius: 12px;
          padding: 10px 12px;
          background: rgba(var(--rgb-primary-text-color), 0.03);
        }
        .toggle-copy {
          display: grid;
          gap: 2px;
        }
        .toggle-label {
          font-size: 0.9rem;
          font-weight: 600;
        }
        .toggle-hint {
          font-size: 0.78rem;
          opacity: 0.72;
        }
      </style>
      <div class="editor">
        <div class="section">
          <div class="section-title">Data source</div>
          <div class="section-copy">Choose which Medication Tracker registry sensor this card should read from.</div>
          <div class="field">
            <label class="label" for="entity">Registry entity</label>
            <select id="entity">${entityOptions}</select>
            <div class="hint">If you only have one registry sensor, the default choice is usually correct.</div>
          </div>
          <div class="field">
            <label class="label" for="title">Card title</label>
            <input id="title" type="text" value="${this._config.title || ""}">
            <div class="hint">Shown at the top of the card.</div>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Layout</div>
          <div class="section-copy">Control the overall structure before choosing which details to show.</div>
          <div class="field">
            <label class="label" for="max_rows">Maximum medications to show</label>
            <input id="max_rows" type="number" min="0" step="1" value="${Number(this._config.max_rows || 0)}">
            <div class="hint">Use 0 to show every tracked medication.</div>
          </div>
          <div class="toggle-grid">
            ${this._toggle("show_header", "Show header", "Displays the card title and tracked count.")}
            ${this._toggle("show_summary", "Show summary tiles", "Shows quick counts for medications, due now, missed, and refill needs.")}
            ${this._toggle("compact_rows", "Use compact rows", "Makes each medication row shorter and denser.")}
            ${this._toggle("show_actions", "Show quick actions", "Adds the Log Dose, Next Dose, and Status buttons.")}
          </div>
        </div>

        <div class="section">
          <div class="section-title">Summary tiles</div>
          <div class="section-copy">Choose which quick totals appear at the top of the card.</div>
          <div class="toggle-grid">
            ${this._toggle("show_summary_medications", "Medication total", "Shows how many medications are currently tracked.")}
            ${this._toggle("show_summary_due_now", "Due now total", "Shows how many medications are currently due.")}
            ${this._toggle("show_summary_missed", "Missed total", "Shows how many medications have a missed dose.")}
            ${this._toggle("show_summary_refill", "Refill total", "Shows how many medications need refilling soon.")}
          </div>
        </div>

        <div class="section">
          <div class="section-title">Medication row details</div>
          <div class="section-copy">Turn individual parts of each medication row on or off.</div>
          <div class="toggle-grid">
            ${this._toggle("show_status_chip", "Status chip", "Shows the current status like On Track or Due Now.")}
            ${this._toggle("show_profile_name", "Person or pet name", "Shows who the medication belongs to.")}
            ${this._toggle("show_dosage", "Dose or strength", "Shows the saved dose in the main row header.")}
            ${this._toggle("show_purpose", "Purpose", "Shows why the medication is taken if stored.")}
            ${this._toggle("show_next_dose", "Next dose", "Shows the next scheduled dose time.")}
            ${this._toggle("show_last_taken", "Last taken", "Shows the most recent logged dose.")}
            ${this._toggle("show_caregiver", "Caregiver", "Shows the assigned caregiver when one is set.")}
            ${this._toggle("show_schedule", "Schedule", "Shows the saved daily schedule times.")}
            ${this._toggle("show_compliance", "Compliance", "Shows the medication compliance percentage.")}
          </div>
        </div>
      </div>
    `;

    this.querySelectorAll("input, select").forEach((element) => {
      element.addEventListener("change", () => this._valueChanged());
    });
  }

  _toggle(key, label, hint) {
    const checked = this._config[key] ? "checked" : "";
    return `
      <label class="toggle">
        <div class="toggle-copy">
          <span class="toggle-label">${label}</span>
          <span class="toggle-hint">${hint}</span>
        </div>
        <input data-key="${key}" type="checkbox" ${checked}>
      </label>
    `;
  }

  _entityOptions() {
    const selected = this._config.entity;
    const entities = Object.keys(this._hass?.states || {})
      .filter((entityId) => entityId.startsWith("sensor.") && entityId.includes("medication"))
      .sort();

    if (!entities.length) {
      return `<option value="${selected}" selected>${selected}</option>`;
    }

    if (!entities.includes(selected)) {
      entities.unshift(selected);
    }

    return entities
      .map((entityId) => `<option value="${entityId}" ${entityId === selected ? "selected" : ""}>${entityId}</option>`)
      .join("");
  }

  _valueChanged() {
    const title = this.querySelector("#title")?.value?.trim();
    const maxRowsValue = this.querySelector("#max_rows")?.value;
    const newConfig = {
      ...this._config,
      entity: this.querySelector("#entity")?.value || this._config.entity,
      title: title || DEFAULT_CONFIG.title,
      max_rows: Number(maxRowsValue || 0),
    };

    this.querySelectorAll('input[type="checkbox"][data-key]').forEach((checkbox) => {
      newConfig[checkbox.dataset.key] = checkbox.checked;
    });

    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }
}

customElements.define("medication-tracker-card", MedicationTrackerCard);
customElements.define("medication-tracker-card-editor", MedicationTrackerCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "medication-tracker-card",
  name: "Medication Tracker Card",
  description: "Registry view with customizable medication details, status, and quick actions.",
});
