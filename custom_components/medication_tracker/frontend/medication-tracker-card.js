const REGISTRY_DEFAULT_CONFIG = {
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
  collapsible_rows: true,
  expand_first_row: false,
  max_rows: 0,
};

const WEEKLY_DEFAULT_CONFIG = {
  type: "custom:medication-tracker-weekly-card",
  entity: "sensor.medication_tracker_medication_registry",
  title: "Weekly Pill Box",
  profile_name: "",
  today_only: false,
  layout_mode: "horizontal",
  show_header: true,
  show_summary: true,
  show_status_chip: true,
  show_times: true,
  show_dosage: true,
  show_purpose: false,
  show_next_dose: true,
  show_last_taken: false,
  show_caregiver: false,
  show_compliance: false,
  show_actions: true,
  show_empty_days: true,
  compact_rows: false,
  collapsible_items: true,
  expand_today: true,
  days_to_show: 7,
  max_items_per_day: 0,
};

function getEntityRows(hass, entityId) {
  return hass.states[entityId]?.attributes?.rows || [];
}

function formatDate(value, fallback) {
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

function buildOccurrenceKey(targetDate, schedule) {
  const [hours = "0", minutes = "0"] = String(schedule || "00:00").split(":");
  const occurrence = new Date(targetDate);
  occurrence.setHours(Number(hours), Number(minutes), 0, 0);

  const year = occurrence.getFullYear();
  const month = String(occurrence.getMonth() + 1).padStart(2, "0");
  const day = String(occurrence.getDate()).padStart(2, "0");
  const hour = String(occurrence.getHours()).padStart(2, "0");
  const minute = String(occurrence.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function dispatchMoreInfo(target, entityId) {
  target.dispatchEvent(
    new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    })
  );
}

function registryEntityOptions(hass, selected) {
  const entities = Object.keys(hass?.states || {})
    .filter((entityId) => entityId.startsWith("sensor.") && entityId.includes("medication"))
    .sort();

  if (!entities.length) {
    return `<option value="${selected}" selected>${selected}</option>`;
  }

  if (selected && !entities.includes(selected)) {
    entities.unshift(selected);
  }

  return entities
    .map((entityId) => `<option value="${entityId}" ${entityId === selected ? "selected" : ""}>${entityId}</option>`)
    .join("");
}

function profileOptions(rows, selected) {
  const profiles = [...new Set(rows.map((row) => row.profile_name).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b)
  );
  const options = [`<option value="" ${selected === "" ? "selected" : ""}>All people and pets</option>`];
  profiles.forEach((profile) => {
    options.push(`<option value="${profile}" ${profile === selected ? "selected" : ""}>${profile}</option>`);
  });
  return options.join("");
}

function baseEditorStyles() {
  return `
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
  `;
}

function toggleMarkup(config, key, label, hint) {
  const checked = config[key] ? "checked" : "";
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

class MedicationTrackerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("medication-tracker-card-editor");
  }

  static getStubConfig() {
    return { ...REGISTRY_DEFAULT_CONFIG };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }

    this._config = {
      ...REGISTRY_DEFAULT_CONFIG,
      ...config,
    };
    this._expandedRows = new Set();
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
        .row-header {
          cursor: pointer;
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
        .expand-icon {
          font-size: 0.95rem;
          opacity: 0.72;
          margin-left: 8px;
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
        .chip.taken {
          background: rgba(2, 119, 189, 0.15);
          color: #0277bd;
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
        .row-content.hidden {
          display: none;
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
    const rows = [...getEntityRows(this._hass, this._config.entity)];
    this._header.classList.toggle("hidden", !this._config.show_header);
    this._summary.classList.toggle("hidden", !this._config.show_summary);

    if (!this._hass.states[this._config.entity]) {
      this._header.innerHTML = `<div class="title">${this._config.title}</div>`;
      this._summary.innerHTML = "";
      this._table.innerHTML = `<div class="empty">Entity not found: ${this._config.entity}</div>`;
      return;
    }

    let visibleRows = rows;
    if (Number(this._config.max_rows) > 0) {
      visibleRows = visibleRows.slice(0, Number(this._config.max_rows));
    }

    if (this._config.collapsible_rows && this._config.expand_first_row && visibleRows.length && !this._expandedRows.size) {
      this._expandedRows.add(visibleRows[0].medication_id);
    }

    this._header.innerHTML = this._config.show_header
      ? `<div class="title">${this._config.title}</div><div class="meta">${visibleRows.length} tracked</div>`
      : "";

    const summaryTiles = [];
    if (this._config.show_summary_medications) {
      summaryTiles.push(["Medications", visibleRows.length]);
    }
    if (this._config.show_summary_due_now) {
      summaryTiles.push(["Due Now", visibleRows.filter((row) => row.due_now).length]);
    }
    if (this._config.show_summary_missed) {
      summaryTiles.push(["Missed", visibleRows.reduce((total, row) => total + Number(row.missed_doses || 0), 0)]);
    }
    if (this._config.show_summary_refill) {
      summaryTiles.push(["Refill", visibleRows.filter((row) => row.needs_refill).length]);
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

    if (!visibleRows.length) {
      this._table.innerHTML = `<div class="empty">No medications are currently tracked.</div>`;
      return;
    }

    this._table.innerHTML = visibleRows
      .map((row) => {
        const statusClass = (row.status || "On Track").toLowerCase().replace(/\s+/g, "-");
        const details = [];
        const metaParts = [];
        const isExpanded = !this._config.collapsible_rows || this._expandedRows.has(row.medication_id);

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
          details.push(this._detail("Next dose", formatDate(row.next_dose, "Not scheduled")));
        }
        if (this._config.show_last_taken) {
          details.push(this._detail("Last taken", formatDate(row.last_taken, "Not logged")));
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
            <div class="row-header" data-row-toggle="${row.medication_id}">
              <div class="row-top">
                <div>
                  <div class="name">
                    ${row.medication_name}
                    ${this._config.collapsible_rows ? `<span class="expand-icon">${isExpanded ? "▾" : "▸"}</span>` : ""}
                  </div>
                  ${metaParts.length ? `<div class="meta">${metaParts.join(" | ")}</div>` : ""}
                </div>
                ${this._config.show_status_chip ? `<div class="chip ${statusClass}">${row.status}</div>` : ""}
              </div>
            </div>
            <div class="row-content ${isExpanded ? "" : "hidden"}">
              ${details.length ? `<div class="details">${details.join("")}</div>` : ""}
              ${
                this._config.show_actions
                  ? `
                    <div class="actions">
                      <button class="action" data-action="log" data-entity="${row.button_entity_id}">Log Dose</button>
                      <button class="action secondary" data-action="more-info" data-entity="${row.next_dose_entity_id}">Next Dose</button>
                      <button class="action secondary" data-action="more-info" data-entity="${row.due_now_entity_id}">Status</button>
                    </div>
                  `
                  : ""
              }
            </div>
          </div>
        `;
      })
      .join("");

    this._table.querySelectorAll("[data-row-toggle]").forEach((rowHeader) => {
      rowHeader.onclick = () => {
        if (!this._config.collapsible_rows) {
          return;
        }
        if (this._expandedRows.has(rowHeader.dataset.rowToggle)) {
          this._expandedRows.delete(rowHeader.dataset.rowToggle);
        } else {
          this._expandedRows.add(rowHeader.dataset.rowToggle);
        }
        this._update();
      };
    });

    this._table.querySelectorAll("button[data-action]").forEach((button) => {
      button.onclick = async (event) => {
        event.stopPropagation();
        if (button.dataset.action === "log") {
          await this._hass.callService("button", "press", { entity_id: button.dataset.entity });
          return;
        }
        dispatchMoreInfo(this, button.dataset.entity);
      };
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
}

class MedicationTrackerWeeklyCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("medication-tracker-weekly-card-editor");
  }

  static getStubConfig() {
    return { ...WEEKLY_DEFAULT_CONFIG };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }

    this._config = {
      ...WEEKLY_DEFAULT_CONFIG,
      ...config,
    };
    this._expandedItems = new Set();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._card) {
      this._renderCard();
    }
    this._update();
  }

  getCardSize() {
    if (this._config?.today_only) {
      return this._config?.compact_rows ? 4 : 5;
    }
    return this._config?.compact_rows ? 6 : 8;
  }

  _renderCard() {
    const card = document.createElement("ha-card");
    card.innerHTML = `
      <style>
        .wrap {
          padding: 14px;
        }
        .header {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
        }
        .header.hidden,
        .summary.hidden {
          display: none;
        }
        .title {
          font-size: 1.18rem;
          font-weight: 700;
          letter-spacing: -0.02em;
        }
        .subtitle {
          opacity: 0.7;
          font-size: 0.84rem;
        }
        .summary {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
          gap: 8px;
          margin-bottom: 12px;
        }
        .summary-tile {
          border-radius: 12px;
          padding: 10px;
          background: rgba(var(--rgb-primary-color), 0.06);
          border: 1px solid rgba(var(--rgb-primary-color), 0.12);
        }
        .summary-label {
          font-size: 0.74rem;
          opacity: 0.72;
          margin-bottom: 3px;
        }
        .summary-value {
          font-size: 1rem;
          font-weight: 700;
        }
        .week-grid {
          display: grid;
          gap: 10px;
        }
        .week-grid.horizontal {
          grid-auto-flow: column;
          grid-auto-columns: minmax(190px, 1fr);
          overflow-x: auto;
          padding-bottom: 2px;
          scroll-snap-type: x proximity;
        }
        .week-grid.vertical {
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        }
        .day-box {
          border: 1px solid var(--divider-color);
          border-radius: 16px;
          padding: 12px;
          background:
            linear-gradient(180deg, rgba(var(--rgb-primary-color), 0.05), rgba(var(--rgb-primary-color), 0.015)),
            rgba(var(--rgb-primary-text-color), 0.015);
          min-width: 0;
        }
        .week-grid.horizontal .day-box {
          scroll-snap-align: start;
        }
        .day-box.today {
          border-color: rgba(var(--rgb-primary-color), 0.35);
          box-shadow: inset 0 0 0 1px rgba(var(--rgb-primary-color), 0.12);
        }
        .day-top {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 10px;
        }
        .day-name {
          font-size: 0.95rem;
          font-weight: 700;
        }
        .day-date {
          font-size: 0.78rem;
          opacity: 0.72;
        }
        .day-count {
          font-size: 0.76rem;
          opacity: 0.72;
        }
        .day-list {
          display: grid;
          gap: 6px;
        }
        .pill {
          border-radius: 14px;
          background: rgba(var(--rgb-primary-text-color), 0.03);
          border: 1px solid rgba(var(--rgb-primary-text-color), 0.06);
          overflow: hidden;
        }
        .pill.compact {
          border-radius: 12px;
        }
        .pill-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 10px;
          padding: 9px 10px;
          cursor: pointer;
        }
        .pill-name {
          font-weight: 700;
          font-size: 0.9rem;
          line-height: 1.2;
        }
        .pill-meta {
          font-size: 0.79rem;
          opacity: 0.72;
          margin-top: 2px;
        }
        .pill-body {
          padding: 0 10px 10px;
        }
        .pill-body.hidden {
          display: none;
        }
        .pill-detail {
          display: grid;
          gap: 4px;
          margin-bottom: 8px;
        }
        .pill-detail:last-of-type {
          margin-bottom: 10px;
        }
        .pill-detail-label {
          font-size: 0.72rem;
          opacity: 0.68;
        }
        .pill-detail-value {
          font-size: 0.86rem;
          font-weight: 600;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .action {
          border: 0;
          border-radius: 10px;
          padding: 8px 10px;
          font: inherit;
          cursor: pointer;
          background: var(--primary-color);
          color: var(--text-primary-color);
          font-weight: 700;
          font-size: 0.8rem;
        }
        .action.secondary {
          background: rgba(var(--rgb-primary-text-color), 0.07);
          color: var(--primary-text-color);
        }
        .chip {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 0.7rem;
          font-weight: 700;
          white-space: nowrap;
        }
        .chip.on-track {
          background: rgba(46, 125, 50, 0.14);
          color: #2e7d32;
        }
        .chip.taken {
          background: rgba(2, 119, 189, 0.15);
          color: #0277bd;
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
        .expand-icon {
          margin-left: 6px;
          opacity: 0.7;
        }
        .empty {
          padding: 10px;
          border-radius: 12px;
          background: rgba(var(--rgb-primary-text-color), 0.03);
          opacity: 0.72;
          font-size: 0.82rem;
        }
      </style>
      <div class="wrap">
        <div class="header" id="header"></div>
        <div class="summary" id="summary"></div>
        <div class="week-grid" id="week-grid"></div>
      </div>
    `;

    this._card = card;
    this._header = card.querySelector("#header");
    this._summary = card.querySelector("#summary");
    this._weekGrid = card.querySelector("#week-grid");
    this.appendChild(card);
  }

  _update() {
    const entityExists = this._hass.states[this._config.entity];
    const rows = getEntityRows(this._hass, this._config.entity);
    const filteredRows = this._config.profile_name
      ? rows.filter((row) => row.profile_name === this._config.profile_name)
      : rows;

    this._header.classList.toggle("hidden", !this._config.show_header);
    this._summary.classList.toggle("hidden", !this._config.show_summary);

    if (!entityExists) {
      this._header.innerHTML = `<div class="title">${this._config.title}</div>`;
      this._summary.innerHTML = "";
      this._weekGrid.innerHTML = `<div class="empty">Entity not found: ${this._config.entity}</div>`;
      return;
    }

    const selectedLabel = this._config.profile_name || "All people and pets";
    const scopeLabel = this._config.today_only
      ? "Today only"
      : `${Math.max(1, Number(this._config.days_to_show || 7))} day view`;
    this._header.innerHTML = this._config.show_header
      ? `
        <div>
          <div class="title">${this._config.title}</div>
          <div class="subtitle">${selectedLabel} | ${scopeLabel}</div>
        </div>
        <div class="subtitle">${filteredRows.length} medications</div>
      `
      : "";

    const dayItems = this._buildWeeklySchedule(filteredRows);
    const totalEntries = dayItems.reduce((total, day) => total + day.items.length, 0);
    const dueEntries = filteredRows.filter((row) => row.due_now).length;
    const refillEntries = filteredRows.filter((row) => row.needs_refill).length;
    const missedEntries = filteredRows.reduce((total, row) => total + Number(row.missed_doses || 0), 0);

    const summaryTiles = [
      ["Week entries", totalEntries],
      ["Medications", filteredRows.length],
      ["Due now", dueEntries],
      ["Refill", refillEntries],
      ["Missed", missedEntries],
    ];

    this._summary.innerHTML = this._config.show_summary
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

    const visibleDays = this._config.show_empty_days ? dayItems : dayItems.filter((day) => day.items.length);
    if (!visibleDays.length) {
      this._weekGrid.innerHTML = `<div class="empty">No medications matched this view.</div>`;
      return;
    }

    this._weekGrid.className = `week-grid ${this._config.layout_mode === "vertical" ? "vertical" : "horizontal"}`;

    if (this._config.collapsible_items && this._config.expand_today) {
      const todayBox = visibleDays.find((day) => day.isToday && day.items.length);
      if (todayBox) {
        todayBox.items.forEach((item, index) => {
          if (index === 0 && !this._expandedItems.size) {
            this._expandedItems.add(item.itemId);
          }
        });
      }
    }

    this._weekGrid.innerHTML = visibleDays
      .map((day) => {
        const items = Number(this._config.max_items_per_day) > 0
          ? day.items.slice(0, Number(this._config.max_items_per_day))
          : day.items;

        return `
          <div class="day-box ${day.isToday ? "today" : ""}">
            <div class="day-top">
              <div>
                <div class="day-name">${day.dayName}</div>
                <div class="day-date">${day.dateLabel}</div>
              </div>
              <div class="day-count">${items.length} scheduled</div>
            </div>
            <div class="day-list">
              ${
                items.length
                  ? items.map((item) => this._renderWeeklyItem(item)).join("")
                  : `<div class="empty">No medications scheduled.</div>`
              }
            </div>
          </div>
        `;
      })
      .join("");

    this._weekGrid.querySelectorAll("[data-weekly-toggle]").forEach((button) => {
      button.onclick = () => {
        if (!this._config.collapsible_items) {
          return;
        }
        const itemId = button.dataset.weeklyToggle;
        if (this._expandedItems.has(itemId)) {
          this._expandedItems.delete(itemId);
        } else {
          this._expandedItems.add(itemId);
        }
        this._update();
      };
    });

    this._weekGrid.querySelectorAll("button[data-action]").forEach((button) => {
      button.onclick = async (event) => {
        event.stopPropagation();
        if (button.dataset.action === "log") {
          await this._hass.callService("button", "press", { entity_id: button.dataset.entity });
          return;
        }
        dispatchMoreInfo(this, button.dataset.entity);
      };
    });
  }

  _renderWeeklyItem(item) {
    const statusClass = (item.status || "On Track").toLowerCase().replace(/\s+/g, "-");
    const metaParts = [];
    const detailBlocks = [];
    const isExpanded = !this._config.collapsible_items || this._expandedItems.has(item.itemId);

    if (this._config.show_times) {
      metaParts.push(item.schedule);
    }
    if (this._config.show_dosage) {
      metaParts.push(item.dosage || "Dose not set");
    }
    if (this._config.show_purpose) {
      detailBlocks.push(["Purpose", item.purpose || "Not set"]);
    }
    if (this._config.show_next_dose) {
      detailBlocks.push(["Next dose", formatDate(item.next_dose, "Not scheduled")]);
    }
    if (this._config.show_last_taken) {
      detailBlocks.push(["Last taken", formatDate(item.last_taken, "Not logged")]);
    }
    if (this._config.show_caregiver) {
      detailBlocks.push(["Caregiver", item.caregiver_name || "Not assigned"]);
    }
    if (this._config.show_compliance) {
      detailBlocks.push(["Compliance", `${item.compliance_percentage ?? "0"}%`]);
    }

    return `
      <div class="pill ${this._config.compact_rows ? "compact" : ""}">
        <div class="pill-head" data-weekly-toggle="${item.itemId}">
          <div>
            <div class="pill-name">
              ${item.medication_name}
              ${this._config.collapsible_items ? `<span class="expand-icon">${isExpanded ? "▾" : "▸"}</span>` : ""}
            </div>
            ${metaParts.length ? `<div class="pill-meta">${metaParts.join(" | ")}</div>` : ""}
          </div>
          ${this._config.show_status_chip ? `<div class="chip ${statusClass}">${item.status}</div>` : ""}
        </div>
        <div class="pill-body ${isExpanded ? "" : "hidden"}">
          ${detailBlocks
            .map(
              ([label, value]) => `
                <div class="pill-detail">
                  <div class="pill-detail-label">${label}</div>
                  <div class="pill-detail-value">${value}</div>
                </div>
              `
            )
            .join("")}
          ${
            this._config.show_actions
              ? `
                <div class="actions">
                  <button class="action" data-action="log" data-entity="${item.button_entity_id}">Log Dose</button>
                  <button class="action secondary" data-action="more-info" data-entity="${item.next_dose_entity_id}">Next Dose</button>
                </div>
              `
              : ""
          }
        </div>
      </div>
    `;
  }

  _buildWeeklySchedule(rows) {
    const now = new Date();
    const days = [];
    const totalDays = this._config.today_only ? 1 : Math.max(1, Number(this._config.days_to_show || 7));

    for (let offset = 0; offset < totalDays; offset += 1) {
      const target = new Date(now);
      target.setHours(0, 0, 0, 0);
      target.setDate(target.getDate() + offset);

      const items = [];
      rows.forEach((row) => {
        (row.schedules || []).forEach((schedule) => {
          const occurrenceKey = buildOccurrenceKey(target, schedule);
          items.push({
            ...row,
            schedule,
            dayOffset: offset,
            status: row.schedule_statuses?.[occurrenceKey] || (offset === 0 ? row.status : "On Track"),
            itemId: `${row.medication_id}_${offset}_${schedule}`,
          });
        });
      });

      items.sort((a, b) => {
        if (a.schedule === b.schedule) {
          return a.medication_name.localeCompare(b.medication_name);
        }
        return a.schedule.localeCompare(b.schedule);
      });

      days.push({
        isToday: offset === 0,
        dayName: new Intl.DateTimeFormat(undefined, { weekday: "long" }).format(target),
        dateLabel: new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(target),
        items,
      });
    }

    return days;
  }
}

class MedicationTrackerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      ...REGISTRY_DEFAULT_CONFIG,
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

    const entityOptions = registryEntityOptions(this._hass, this._config.entity);
    this.innerHTML = `
      <style>${baseEditorStyles()}</style>
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
            ${toggleMarkup(this._config, "show_header", "Show header", "Displays the card title and tracked count.")}
            ${toggleMarkup(this._config, "show_summary", "Show summary tiles", "Shows quick counts for medications, due now, missed, and refill needs.")}
            ${toggleMarkup(this._config, "compact_rows", "Use compact rows", "Makes each medication row shorter and denser.")}
            ${toggleMarkup(this._config, "collapsible_rows", "Collapse medication rows", "Shows each medication as a click-to-expand panel instead of leaving every row open.")}
            ${toggleMarkup(this._config, "expand_first_row", "Open first medication", "Expands the first medication automatically when collapsed rows are enabled.")}
            ${toggleMarkup(this._config, "show_actions", "Show quick actions", "Adds the Log Dose, Next Dose, and Status buttons.")}
          </div>
        </div>

        <div class="section">
          <div class="section-title">Summary tiles</div>
          <div class="section-copy">Choose which quick totals appear at the top of the card.</div>
          <div class="toggle-grid">
            ${toggleMarkup(this._config, "show_summary_medications", "Medication total", "Shows how many medications are currently tracked.")}
            ${toggleMarkup(this._config, "show_summary_due_now", "Due now total", "Shows how many medications are currently due.")}
            ${toggleMarkup(this._config, "show_summary_missed", "Missed total", "Shows how many medications have a missed dose.")}
            ${toggleMarkup(this._config, "show_summary_refill", "Refill total", "Shows how many medications need refilling soon.")}
          </div>
        </div>

        <div class="section">
          <div class="section-title">Medication row details</div>
          <div class="section-copy">Turn individual parts of each medication row on or off.</div>
          <div class="toggle-grid">
            ${toggleMarkup(this._config, "show_status_chip", "Status chip", "Shows the current status like On Track or Due Now.")}
            ${toggleMarkup(this._config, "show_profile_name", "Person or pet name", "Shows who the medication belongs to.")}
            ${toggleMarkup(this._config, "show_dosage", "Dose or strength", "Shows the saved dose in the main row header.")}
            ${toggleMarkup(this._config, "show_purpose", "Purpose", "Shows why the medication is taken if stored.")}
            ${toggleMarkup(this._config, "show_next_dose", "Next dose", "Shows the next scheduled dose time.")}
            ${toggleMarkup(this._config, "show_last_taken", "Last taken", "Shows the most recent logged dose.")}
            ${toggleMarkup(this._config, "show_caregiver", "Caregiver", "Shows the assigned caregiver when one is set.")}
            ${toggleMarkup(this._config, "show_schedule", "Schedule", "Shows the saved daily schedule times.")}
            ${toggleMarkup(this._config, "show_compliance", "Compliance", "Shows the medication compliance percentage.")}
          </div>
        </div>
      </div>
    `;

    this.querySelectorAll("input, select").forEach((element) => {
      element.addEventListener("change", () => this._valueChanged());
    });
  }

  _valueChanged() {
    const title = this.querySelector("#title")?.value?.trim();
    const maxRowsValue = this.querySelector("#max_rows")?.value;
    const newConfig = {
      ...this._config,
      entity: this.querySelector("#entity")?.value || this._config.entity,
      title: title || REGISTRY_DEFAULT_CONFIG.title,
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

class MedicationTrackerWeeklyCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      ...WEEKLY_DEFAULT_CONFIG,
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

    const entityOptions = registryEntityOptions(this._hass, this._config.entity);
    const rows = getEntityRows(this._hass, this._config.entity);
    const profileSelect = profileOptions(rows, this._config.profile_name || "");

    this.innerHTML = `
      <style>${baseEditorStyles()}</style>
      <div class="editor">
        <div class="section">
          <div class="section-title">Data source</div>
          <div class="section-copy">Choose the registry sensor and which person or pet this weekly pill box should focus on.</div>
          <div class="field">
            <label class="label" for="entity">Registry entity</label>
            <select id="entity">${entityOptions}</select>
            <div class="hint">This should usually be your Medication Tracker registry sensor.</div>
          </div>
          <div class="field">
            <label class="label" for="profile_name">Person or pet</label>
            <select id="profile_name">${profileSelect}</select>
            <div class="hint">Choose one person or pet for a true pill-box view, or leave it on all.</div>
          </div>
          <div class="field">
            <label class="label" for="title">Card title</label>
            <input id="title" type="text" value="${this._config.title || ""}">
            <div class="hint">Shown at the top of the weekly card.</div>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Layout</div>
          <div class="section-copy">Keep the weekly view clean and compact, or show more detail when needed.</div>
          <div class="field">
            <label class="label" for="layout_mode">Layout mode</label>
            <select id="layout_mode">
              <option value="horizontal" ${this._config.layout_mode === "horizontal" ? "selected" : ""}>Horizontal day strip</option>
              <option value="vertical" ${this._config.layout_mode === "vertical" ? "selected" : ""}>Vertical stacked days</option>
            </select>
            <div class="hint">Horizontal keeps the card shorter. Vertical is easier to scan down a page.</div>
          </div>
          <div class="field">
            <label class="label" for="days_to_show">Days to show</label>
            <input id="days_to_show" type="number" min="1" max="7" step="1" value="${Number(this._config.days_to_show || 7)}">
            <div class="hint">Use up to 7 days for a full weekly pill-box layout.</div>
          </div>
          <div class="field">
            <label class="label" for="max_items_per_day">Maximum medications per day box</label>
            <input id="max_items_per_day" type="number" min="0" step="1" value="${Number(this._config.max_items_per_day || 0)}">
            <div class="hint">Use 0 to show every scheduled item in each day.</div>
          </div>
          <div class="toggle-grid">
            ${toggleMarkup(this._config, "show_header", "Show header", "Displays the title and current person or pet.")}
            ${toggleMarkup(this._config, "show_summary", "Show weekly summary", "Shows quick totals for the selected weekly view.")}
            ${toggleMarkup(this._config, "today_only", "Show today only", "Collapses the card down to just today's medication box for a much smaller footprint.")}
            ${toggleMarkup(this._config, "show_empty_days", "Show empty day boxes", "Keeps all seven boxes visible even if no medications are scheduled.")}
            ${toggleMarkup(this._config, "compact_rows", "Use compact medication items", "Makes the items inside each day box tighter and shorter.")}
            ${toggleMarkup(this._config, "collapsible_items", "Collapse medication items", "Lets each medication entry open only when clicked.")}
            ${toggleMarkup(this._config, "expand_today", "Open today's first item", "Expands the first medication scheduled today automatically.")}
          </div>
        </div>

        <div class="section">
          <div class="section-title">Medication details</div>
          <div class="section-copy">Choose which details are visible inside each day box.</div>
          <div class="toggle-grid">
            ${toggleMarkup(this._config, "show_status_chip", "Status chip", "Shows the medication status like On Track or Needs Refill.")}
            ${toggleMarkup(this._config, "show_times", "Show schedule times", "Shows the scheduled time in each medication item.")}
            ${toggleMarkup(this._config, "show_dosage", "Show dose or strength", "Shows the stored dosage beside the time.")}
            ${toggleMarkup(this._config, "show_purpose", "Show purpose", "Shows why the medication is taken if stored.")}
            ${toggleMarkup(this._config, "show_next_dose", "Show next dose", "Shows the next scheduled dose time in the expanded detail area.")}
            ${toggleMarkup(this._config, "show_last_taken", "Show last taken", "Shows the most recent logged dose in the expanded detail area.")}
            ${toggleMarkup(this._config, "show_caregiver", "Show caregiver", "Shows the assigned caregiver if one is set.")}
            ${toggleMarkup(this._config, "show_compliance", "Show compliance", "Shows the compliance percentage in the expanded detail area.")}
            ${toggleMarkup(this._config, "show_actions", "Show quick actions", "Adds the Log Dose and Next Dose buttons.")}
          </div>
        </div>
      </div>
    `;

    this.querySelectorAll("input, select").forEach((element) => {
      element.addEventListener("change", () => this._valueChanged());
    });
  }

  _valueChanged() {
    const title = this.querySelector("#title")?.value?.trim();
    const daysToShowValue = this.querySelector("#days_to_show")?.value;
    const maxItemsValue = this.querySelector("#max_items_per_day")?.value;
    const newConfig = {
      ...this._config,
      entity: this.querySelector("#entity")?.value || this._config.entity,
      profile_name: this.querySelector("#profile_name")?.value || "",
      layout_mode: this.querySelector("#layout_mode")?.value || "horizontal",
      title: title || WEEKLY_DEFAULT_CONFIG.title,
      days_to_show: Math.min(7, Math.max(1, Number(daysToShowValue || 7))),
      max_items_per_day: Number(maxItemsValue || 0),
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
customElements.define("medication-tracker-weekly-card", MedicationTrackerWeeklyCard);
customElements.define("medication-tracker-weekly-card-editor", MedicationTrackerWeeklyCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "medication-tracker-card",
  name: "Medication Tracker Card",
  description: "Registry view with customizable medication details, status, and quick actions.",
});
window.customCards.push({
  type: "medication-tracker-weekly-card",
  name: "Medication Tracker Weekly Card",
  description: "Weekly pill-box style layout for one person or pet, with simple tracking and quick actions.",
});
