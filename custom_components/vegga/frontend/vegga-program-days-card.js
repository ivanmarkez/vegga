const VEGGA_PROGRAM_DAYS_VERSION = "0.5.25";

class VeggaProgramDaysCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._drafts = new Map();
    this._busy = new Set();
    this._messages = new Map();
  }

  static getStubConfig() {
    return {
      controller: "vivero_agronic_17669",
      title: "Días de riego",
    };
  }

  setConfig(config) {
    if (!config?.controller) throw new Error("Debes indicar controller.");
    this._config = {
      title: "Días de riego",
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { rows: 8, columns: 12, min_rows: 4, min_columns: 6 };
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _number(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  _belongs(state) {
    const configured = String(this._config?.controller || "");
    const deviceId = String(state?.attributes?.vegga_device_id ?? state?.attributes?.device_id ?? "");
    if (deviceId && (configured === deviceId || configured.endsWith(`_${deviceId}`))) return true;
    const stem = String(state?.entity_id || "").split(".")[1] || "";
    return stem.startsWith(`${configured}_`);
  }

  _programs() {
    const grouped = new Map();

    Object.values(this._hass?.states || {}).forEach((state) => {
      if (!state.entity_id?.startsWith("sensor.")) return;
      if (!this._belongs(state)) return;

      const programs = Array.isArray(state.attributes?.programs)
        ? state.attributes.programs
        : [];

      programs.forEach((program) => {
        const number = this._number(program?.program_number);
        if (number === null) return;

        const scheduleType = String(program?.schedule_type || "");
        const weekdays = program?.weekdays && typeof program.weekdays === "object"
          ? program.weekdays
          : null;

        if (scheduleType !== "weekdays" || !weekdays) return;

        const key = String(number);
        if (!grouped.has(key)) {
          grouped.set(key, {
            number,
            name: String(program?.program_name || `Programa ${number}`),
            weekdays: {
              monday: Boolean(weekdays.monday),
              tuesday: Boolean(weekdays.tuesday),
              wednesday: Boolean(weekdays.wednesday),
              thursday: Boolean(weekdays.thursday),
              friday: Boolean(weekdays.friday),
              saturday: Boolean(weekdays.saturday),
              sunday: Boolean(weekdays.sunday),
            },
          });
        }
      });
    });

    return Array.from(grouped.values()).sort((a, b) => a.number - b.number);
  }

  _draft(program) {
    const key = String(program.number);
    if (!this._drafts.has(key)) {
      this._drafts.set(key, { ...program.weekdays });
    }
    return this._drafts.get(key);
  }

  _sameDays(a, b) {
    return [
      "monday", "tuesday", "wednesday", "thursday",
      "friday", "saturday", "sunday",
    ].every((key) => Boolean(a[key]) === Boolean(b[key]));
  }

  _toggle(programNumber, day) {
    const program = this._programs().find((item) => item.number === programNumber);
    if (!program || this._busy.has(String(programNumber))) return;

    const draft = this._draft(program);
    draft[day] = !draft[day];
    this._messages.delete(String(programNumber));
    this._render();
  }

  _reset(programNumber) {
    const program = this._programs().find((item) => item.number === programNumber);
    if (!program) return;

    this._drafts.set(String(programNumber), { ...program.weekdays });
    this._messages.delete(String(programNumber));
    this._render();
  }

  async _save(programNumber) {
    if (!this._hass) return;

    const program = this._programs().find((item) => item.number === programNumber);
    if (!program) return;

    const key = String(programNumber);
    const draft = this._draft(program);
    const days = Object.entries(draft)
      .filter(([, enabled]) => enabled)
      .map(([day]) => day);

    this._busy.add(key);
    this._messages.set(key, { type: "info", text: "Guardando…" });
    this._render();

    try {
      await this._hass.callService("vegga", "set_program_days", {
        controller: this._config.controller,
        program: programNumber,
        days,
      });

      this._drafts.delete(key);
      this._messages.set(key, { type: "ok", text: "Días guardados" });
      this._busy.delete(key);
      this._render();

      setTimeout(() => {
        if (this._messages.get(key)?.type === "ok") {
          this._messages.delete(key);
          this._render();
        }
      }, 3000);
    } catch (error) {
      this._busy.delete(key);
      this._messages.set(key, {
        type: "error",
        text: `No se pudo guardar: ${error?.message || error}`,
      });
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;

    const programs = this._programs();
    const dayLabels = [
      ["monday", "L"],
      ["tuesday", "M"],
      ["wednesday", "X"],
      ["thursday", "J"],
      ["friday", "V"],
      ["saturday", "S"],
      ["sunday", "D"],
    ];

    const rows = programs.map((program) => {
      const key = String(program.number);
      const draft = this._draft(program);
      const changed = !this._sameDays(draft, program.weekdays);
      const busy = this._busy.has(key);
      const message = this._messages.get(key);

      return `<section class="program">
        <div class="program-head">
          <div>
            <div class="program-number">P${program.number}</div>
            <div class="program-name">${this._escape(program.name)}</div>
          </div>
          ${changed ? `<span class="changed">Sin guardar</span>` : `<span class="saved">Actual</span>`}
        </div>

        <div class="days">
          ${dayLabels.map(([day, label]) => `
            <button
              class="day ${draft[day] ? "active" : ""}"
              data-program="${program.number}"
              data-day="${day}"
              ${busy ? "disabled" : ""}
              aria-pressed="${draft[day] ? "true" : "false"}"
            >${label}</button>
          `).join("")}
        </div>

        <div class="actions">
          <button class="reset" data-reset="${program.number}" ${!changed || busy ? "disabled" : ""}>
            Deshacer
          </button>
          <button class="save" data-save="${program.number}" ${!changed || busy ? "disabled" : ""}>
            ${busy ? "Guardando…" : "Guardar"}
          </button>
        </div>

        ${message ? `<div class="message ${message.type}">${this._escape(message.text)}</div>` : ""}
      </section>`;
    }).join("");

    this.shadowRoot.innerHTML = `<style>
      :host{display:block}
      ha-card{overflow:hidden}
      .wrap{padding:18px}
      .titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
      h2{margin:0;font-size:1.35rem}
      .version{font-size:.72rem;color:var(--secondary-text-color)}
      .note{margin:0 0 14px;color:var(--secondary-text-color);font-size:.84rem}
      .list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}
      .program{border:1px solid var(--divider-color);border-radius:14px;padding:14px;background:var(--card-background-color)}
      .program-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:12px}
      .program-number{font-size:.76rem;font-weight:800;color:var(--primary-color)}
      .program-name{font-size:1rem;font-weight:750;margin-top:2px}
      .changed,.saved{font-size:.72rem;font-weight:750;padding:4px 8px;border-radius:999px;white-space:nowrap}
      .changed{background:color-mix(in srgb,var(--warning-color,#f9a825) 18%,var(--card-background-color));color:var(--warning-color,#f9a825)}
      .saved{background:var(--secondary-background-color);color:var(--secondary-text-color)}
      .days{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}
      .day{aspect-ratio:1/1;border-radius:50%;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--secondary-text-color);font:inherit;font-weight:800;cursor:pointer;min-width:34px}
      .day.active{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}
      .day:disabled{opacity:.55;cursor:default}
      .actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}
      .actions button{min-height:40px;border-radius:10px;padding:0 14px;font:inherit;font-weight:750;cursor:pointer}
      .actions button:disabled{opacity:.45;cursor:default}
      .reset{border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color)}
      .save{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff)}
      .message{margin-top:9px;font-size:.82rem}
      .message.info{color:var(--primary-color)}
      .message.ok{color:var(--success-color,#2e7d32)}
      .message.error{color:var(--error-color,#d32f2f)}
      .empty{padding:22px;text-align:center;color:var(--secondary-text-color);border:1px solid var(--divider-color);border-radius:14px}
      @media(max-width:700px){
        .wrap{padding:12px}
        h2{font-size:1.15rem}
        .list{grid-template-columns:1fr}
        .program{padding:12px}
        .day{min-width:0;width:100%;font-size:.9rem}
      }
    </style>

    <ha-card>
      <div class="wrap">
        <div class="titlebar">
          <h2>${this._escape(this._config.title)}</h2>
          <span class="version">v${VEGGA_PROGRAM_DAYS_VERSION}</span>
        </div>
        <p class="note">Activa o desactiva los días y pulsa Guardar. Solo se envían los siete campos del calendario semanal.</p>
        ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">No se han encontrado programas con calendario semanal.</div>`}
      </div>
    </ha-card>`;

    this.shadowRoot.querySelectorAll("button.day").forEach((button) => {
      button.addEventListener("click", () => {
        this._toggle(
          Number(button.dataset.program),
          button.dataset.day,
        );
      });
    });

    this.shadowRoot.querySelectorAll("button[data-reset]").forEach((button) => {
      button.addEventListener("click", () => {
        this._reset(Number(button.dataset.reset));
      });
    });

    this.shadowRoot.querySelectorAll("button[data-save]").forEach((button) => {
      button.addEventListener("click", () => {
        this._save(Number(button.dataset.save));
      });
    });
  }
}

if (!customElements.get("vegga-program-days-card")) {
  customElements.define("vegga-program-days-card", VeggaProgramDaysCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "vegga-program-days-card")) {
  window.customCards.push({
    type: "vegga-program-days-card",
    name: "VEGGA - Días de riego",
    description: "Cambia únicamente los días semanales de los programas Agrónic.",
  });
}

console.info(
  `%c VEGGA días de riego ${VEGGA_PROGRAM_DAYS_VERSION} `,
  "color:white;background:#00897b;font-weight:bold;padding:3px 6px;border-radius:4px",
);
