class MedicationTrackerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("medication-tracker-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:medication-tracker-card",
      entity: "sensor.medication_tracker_medication_registry",
      title: "Medication Registry",
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }

    this._config = {
      title: "Medication Registry",
      show_header: true,
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
    return 8;
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
        .row-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 10px;
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
    if (!entity) {
      this._header.innerHTML = `<div class="title">${this._config.title}</div>`;
      this._summary.innerHTML = "";
      this._table.innerHTML = `<div class="empty">Entity not found: ${this._config.entity}</div>`;
      return;
    }

    const rows = entity.attributes.rows || [];
    const medCount = this._safeState("sensor.medication_tracker_medication_count");
    const dueNow = this._safeState("sensor.medication_tracker_due_now_count");
    const missed = this._safeState("sensor.medication_tracker_missed_dose_count");
    const refill = this._safeState("sensor.medication_tracker_refill_needed_count");

    this._header.innerHTML = this._config.show_header
      ? `<div class="title">${this._config.title}</div><div class="meta">${rows.length} tracked</div>`
      : "";

    this._summary.innerHTML = [
      ["Medications", medCount],
      ["Due Now", dueNow],
      ["Missed", missed],
      ["Refill", refill],
    ]
      .map(
        ([label, value]) => `
          <div class="summary-tile">
            <div class="summary-label">${label}</div>
            <div class="summary-value">${value}</div>
          </div>
        `
      )
      .join("");

    if (!rows.length) {
      this._table.innerHTML = `<div class="empty">No medications are currently tracked.</div>`;
      return;
    }

    this._table.innerHTML = rows
      .map((row) => {
        const statusClass = (row.status || "On Track").toLowerCase().replace(/\s+/g, "-");
        return `
          <div class="row">
            <div class="row-top">
              <div>
                <div class="name">${row.medication_name}</div>
                <div class="meta">${row.profile_name} • ${row.dosage || "Dose not set"}</div>
              </div>
              <div class="chip ${statusClass}">${row.status}</div>
            </div>
            <div class="details">
              <div class="detail">
                <div class="detail-label">Purpose</div>
                <div class="detail-value">${row.purpose || "Not set"}</div>
              </div>
              <div class="detail">
                <div class="detail-label">Next dose</div>
                <div class="detail-value">${this._formatDate(row.next_dose, "Not scheduled")}</div>
              </div>
              <div class="detail">
                <div class="detail-label">Last taken</div>
                <div class="detail-value">${this._formatDate(row.last_taken, "Not logged")}</div>
              </div>
              <div class="detail">
                <div class="detail-label">Caregiver</div>
                <div class="detail-value">${row.caregiver_name || "Not assigned"}</div>
              </div>
              <div class="detail">
                <div class="detail-label">Schedule</div>
                <div class="detail-value">${(row.schedules || []).join(", ") || "None"}</div>
              </div>
              <div class="detail">
                <div class="detail-label">Compliance</div>
                <div class="detail-value">${row.compliance_percentage ?? "0"}%</div>
              </div>
            </div>
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
          </div>
        `;
      })
      .join("");

    this._table.querySelectorAll("button[data-action]").forEach((button) => {
      button.onclick = () => this._handleAction(button.dataset.action, button.dataset.entity);
    });
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

customElements.define("medication-tracker-card", MedicationTrackerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "medication-tracker-card",
  name: "Medication Tracker Card",
  description: "Registry view with next dose, status, and quick actions.",
});
