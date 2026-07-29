const CARD_VERSION = "0.4.48";
const MODES = [
  { value: "Automático", icon: "mdi:autorenew", className: "automatico" },
  { value: "Marcha manual", icon: "mdi:play", className: "marcha" },
  { value: "Paro manual", icon: "mdi:stop", className: "paro" },
];

class VeggaSectorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._selectedMode = null;
    this._busy = false;
    this._message = "";
  }

  static getConfigElement() {
    return document.createElement("vegga-sector-card-editor");
  }

  static getStubConfig(hass, entities) {
    const entity = entities?.find((entityId) => entityId.startsWith("select."));
    return entity ? { entity } : {};
  }

  setConfig(config) {
    if (!config?.entity) {
      throw new Error("Debes indicar la entidad select del modo del sector.");
    }
    if (!String(config.entity).startsWith("select.")) {
      throw new Error("La entidad principal debe pertenecer al dominio select.");
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Home Assistant publishes state updates frequently. Do not rebuild the
    // shadow DOM while the confirmation dialog is open, otherwise the button
    // the user is about to confirm disappears underneath the pointer.
    if (this._selectedMode || this._busy) return;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { rows: 3, columns: 6, min_rows: 3, min_columns: 4 };
  }

  _entityState() {
    return this._hass?.states?.[this._config?.entity] || null;
  }

  _friendlyName(stateObj) {
    return (
      this._config?.name ||
      stateObj?.attributes?.friendly_name ||
      this._config?.entity ||
      "Sector VEGGA"
    ).replace(/ Modo de funcionamiento$/i, "");
  }

  _openConfirmation(mode) {
    if (this._busy) return;
    this._selectedMode = mode;
    this._message = "";
    this._render();
    const dialog = this.shadowRoot.querySelector("dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  _closeConfirmation() {
    const dialog = this.shadowRoot.querySelector("dialog");
    if (dialog?.open) dialog.close();
    this._selectedMode = null;
    this._message = "";
    this._render();
  }

  async _confirmChange() {
    if (!this._hass || !this._selectedMode || this._busy) return;
    this._busy = true;
    this._message = "Enviando orden…";
    const targetMode = this._selectedMode;
    this._render();
    this.shadowRoot.querySelector("dialog")?.showModal();

    try {
      await this._hass.callService("select", "select_option", {
        entity_id: this._config.entity,
        option: targetMode,
      });
      this._busy = false;
      this._selectedMode = null;
      this._message = "";
      this._render();
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          bubbles: true,
          composed: true,
          detail: { message: `Modo cambiado a ${targetMode}` },
        })
      );
    } catch (error) {
      console.error("VEGGA: error al cambiar el modo del sector", error);
      this._busy = false;
      this._message = `No se pudo aplicar el cambio: ${error?.message || error}`;
      this._render();
      this.shadowRoot.querySelector("dialog")?.showModal();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const stateObj = this._entityState();
    const currentMode = stateObj?.state || "Desconocido";
    const available = Boolean(stateObj) && stateObj.state !== "unavailable";
    const name = this._friendlyName(stateObj);
    const selected = this._selectedMode;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 18px; overflow: hidden; }
        .header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
        .title { min-width: 0; }
        .name { font-size: 1.1rem; font-weight: 600; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .subtitle { margin-top: 4px; color: var(--secondary-text-color); font-size: .9rem; }
        .status { padding: 5px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; background: var(--secondary-background-color); white-space: nowrap; }
        .status.unavailable { color: var(--error-color); }
        .actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
        button.mode { border: 1px solid var(--divider-color); border-radius: 12px; min-height: 76px; padding: 10px 6px; cursor: pointer; background: var(--card-background-color); color: var(--primary-text-color); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; font: inherit; transition: transform .12s ease, border-color .12s ease, background .12s ease; }
        button.mode:hover:not(:disabled) { transform: translateY(-1px); border-color: var(--primary-color); }
        button.mode:disabled { cursor: default; opacity: .55; }
        button.mode.current { border-width: 2px; border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 12%, var(--card-background-color)); opacity: 1; }
        button.mode ha-icon { --mdc-icon-size: 25px; }
        .automatico ha-icon { color: var(--primary-color); }
        .marcha ha-icon { color: var(--success-color, #2e7d32); }
        .paro ha-icon { color: var(--error-color); }
        .label { font-size: .82rem; line-height: 1.15; text-align: center; }
        dialog { width: min(440px, calc(100vw - 36px)); border: 0; border-radius: 18px; padding: 0; color: var(--primary-text-color); background: var(--card-background-color); box-shadow: 0 12px 42px rgba(0,0,0,.35); }
        dialog::backdrop { background: rgba(0,0,0,.55); }
        .dialog-content { padding: 24px; }
        .dialog-title { display: flex; align-items: center; gap: 10px; font-size: 1.2rem; font-weight: 650; margin-bottom: 16px; }
        .dialog-title ha-icon { color: var(--warning-color, #f57c00); }
        .question { line-height: 1.5; }
        .change { margin: 16px 0; padding: 14px; border-radius: 12px; background: var(--secondary-background-color); }
        .arrow { color: var(--secondary-text-color); padding: 0 7px; }
        .warning { color: var(--secondary-text-color); font-size: .9rem; line-height: 1.4; }
        .message { margin-top: 14px; color: var(--error-color); font-size: .9rem; }
        .message.busy { color: var(--primary-color); }
        .dialog-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 22px; }
        .dialog-actions button { min-height: 40px; padding: 0 16px; border-radius: 10px; font: inherit; font-weight: 600; cursor: pointer; }
        .cancel { border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); }
        .confirm { border: 0; background: var(--primary-color); color: var(--text-primary-color, white); }
        .dialog-actions button:disabled { opacity: .55; cursor: wait; }
        ha-card.compact { padding: 10px; border-radius: 12px; }
        .compact .header { margin-bottom: 8px; }
        .compact .name { font-size: .92rem; }
        .compact .subtitle, .compact .status { display: none; }
        .compact .actions { gap: 5px; }
        .compact button.mode { min-height: 46px; padding: 5px 2px; border-radius: 8px; gap: 2px; }
        .compact button.mode ha-icon { --mdc-icon-size: 19px; }
        .compact .label { font-size: .68rem; }
        @media (max-width: 430px) {
          ha-card { padding: 14px; }
          .actions { gap: 7px; }
          button.mode { min-height: 70px; padding: 8px 3px; }
          .label { font-size: .76rem; }
        }
      </style>
      <ha-card class="${this._config.compact ? "compact" : ""}">
        <div class="header">
          <div class="title">
            <div class="name">${this._escape(name)}</div>
            <div class="subtitle">Modo actual: ${this._escape(currentMode)}</div>
          </div>
          <div class="status ${available ? "" : "unavailable"}">${available ? "Conectado" : "No disponible"}</div>
        </div>
        <div class="actions">
          ${MODES.map(
            (mode) => `
              <button class="mode ${mode.className} ${currentMode === mode.value ? "current" : ""}"
                data-mode="${mode.value}" ${!available || this._busy || currentMode === mode.value ? "disabled" : ""}>
                <ha-icon icon="${mode.icon}"></ha-icon>
                <span class="label">${
                  this._config.compact
                    ? { "Automático": "Auto", "Marcha manual": "Marcha", "Paro manual": "Paro" }[mode.value]
                    : mode.value
                }</span>
              </button>`
          ).join("")}
        </div>
      </ha-card>
      <dialog aria-label="Confirmar cambio de modo">
        <div class="dialog-content">
          <div class="dialog-title"><ha-icon icon="mdi:shield-alert"></ha-icon>Confirmar cambio</div>
          <div class="question">¿Estás seguro de que quieres cambiar <strong>${this._escape(name)}</strong>?</div>
          <div class="change"><strong>${this._escape(currentMode)}</strong><span class="arrow">→</span><strong>${this._escape(selected || "")}</strong></div>
          <div class="warning">La orden se enviará inmediatamente al programador Agrónic.</div>
          ${this._message ? `<div class="message ${this._busy ? "busy" : ""}">${this._escape(this._message)}</div>` : ""}
          <div class="dialog-actions">
            <button class="cancel" ${this._busy ? "disabled" : ""}>Cancelar</button>
            <button class="confirm" ${this._busy ? "disabled" : ""}>${this._busy ? "Enviando…" : "Sí, cambiar modo"}</button>
          </div>
        </div>
      </dialog>
    `;

    this.shadowRoot.querySelectorAll("button.mode").forEach((button) => {
      button.addEventListener("click", () => this._openConfirmation(button.dataset.mode));
    });
    this.shadowRoot.querySelector(".cancel")?.addEventListener("click", () => this._closeConfirmation());
    this.shadowRoot.querySelector(".confirm")?.addEventListener("click", () => this._confirmChange());
    this.shadowRoot.querySelector("dialog")?.addEventListener("cancel", (event) => {
      if (this._busy) event.preventDefault();
      else this._closeConfirmation();
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

class VeggaSectorCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  _valueChanged(key, value) {
    const config = { ...this._config, [key]: value };
    if (!value) delete config[key];
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this.shadowRoot) return;
    const selects = Object.keys(this._hass?.states || {}).filter((id) => id.startsWith("select.") && id.includes("sector"));
    this.shadowRoot.innerHTML = `
      <style>
        .field { margin: 14px 0; }
        label { display:block; margin-bottom:6px; font-weight:600; }
        select, input { box-sizing:border-box; width:100%; min-height:42px; padding:8px; border:1px solid var(--divider-color); border-radius:8px; color:var(--primary-text-color); background:var(--card-background-color); }
        .hint { margin-top:5px; color:var(--secondary-text-color); font-size:.85rem; }
      </style>
      <div class="field">
        <label>Selector del modo</label>
        <select id="entity">
          <option value="">Selecciona una entidad</option>
          ${selects.map((id) => `<option value="${id}" ${this._config.entity === id ? "selected" : ""}>${id}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label>Nombre personalizado (opcional)</label>
        <input id="name" value="${this._config.name || ""}" placeholder="Sector 1 - Frutales">
      </div>
    `;
    this.shadowRoot.querySelector("#entity")?.addEventListener("change", (event) => this._valueChanged("entity", event.target.value));
    this.shadowRoot.querySelector("#name")?.addEventListener("change", (event) => this._valueChanged("name", event.target.value.trim()));
  }
}

class VeggaSectorsGrid extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._entitySignature = "";
  }

  static getStubConfig() {
    return { title: "Control de sectores" };
  }

  setConfig(config) {
    this._config = { title: "Control de sectores", ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const entities = this._sectorEntities();
    const signature = entities.map(([entityId]) => entityId).join("|");
    if (signature !== this._entitySignature || !this.shadowRoot.querySelector(".grid")) {
      this._render(entities);
      return;
    }
    // Preserve the existing sector-card elements (and any open confirmation
    // dialog) and only pass them the new Home Assistant state.
    this.shadowRoot.querySelectorAll("vegga-sector-card").forEach((card) => {
      card.hass = hass;
    });
  }

  _sectorEntities() {
    const requiredModes = MODES.map((mode) => mode.value);
    return Object.entries(this._hass?.states || {})
      .filter(([entityId, stateObj]) => {
        if (!entityId.startsWith("select.")) return false;
        const options = stateObj?.attributes?.options;
        return Array.isArray(options) && requiredModes.every((mode) => options.includes(mode));
      })
      .sort(([, left], [, right]) =>
        String(left?.attributes?.friendly_name || "").localeCompare(
          String(right?.attributes?.friendly_name || ""),
          "es",
          { numeric: true, sensitivity: "base" }
        )
      );
  }

  getCardSize() {
    return Math.max(3, Math.ceil(this._sectorEntities().length / 3) * 3);
  }

  _render(preloadedEntities = null) {
    if (!this.shadowRoot || !this._hass) return;
    const entities = preloadedEntities || this._sectorEntities();
    this._entitySignature = entities.map(([entityId]) => entityId).join("|");
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 12px; }
        .heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 4px 16px; }
        h1 { margin: 0; color: var(--primary-text-color); font-size: 1.55rem; }
        .count { color: var(--secondary-text-color); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(235px, 1fr)); gap: 8px; align-items: start; }
        .empty { padding: 24px; border-radius: 14px; color: var(--secondary-text-color); background: var(--card-background-color); }
        @media (max-width: 430px) {
          :host { padding: 6px; }
          .grid { grid-template-columns: 1fr; gap: 9px; }
          h1 { font-size: 1.25rem; }
        }
      </style>
      <div class="heading">
        <h1>${String(this._config.title || "Control de sectores")}</h1>
        <span class="count">${entities.length} sectores</span>
      </div>
      <div class="grid"></div>
      ${entities.length ? "" : '<div class="empty">No se encontraron controles de sector VEGGA.</div>'}
    `;
    const grid = this.shadowRoot.querySelector(".grid");
    entities.forEach(([entityId]) => {
      const card = document.createElement("vegga-sector-card");
      card.setConfig({ entity: entityId, compact: true });
      card.hass = this._hass;
      grid.appendChild(card);
    });
  }
}

class VeggaProgramCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._busy = false;
  }

  setConfig(config) {
    if (!config?.start_entity || !config?.stop_entity) {
      throw new Error("Faltan los botones de marcha o paro del programa.");
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._busy) this._render();
  }

  async _press(entityId, operation) {
    if (this._busy || !this._hass) return;
    const name = this._config.name || "Programa";
    if (!window.confirm(`¿Confirmas ${operation.toLowerCase()} el programa “${name}”?`)) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          bubbles: true,
          composed: true,
          detail: { message: `${operation}: ${name}` },
        })
      );
    } catch (error) {
      console.error("VEGGA: error al controlar el programa", error);
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          bubbles: true,
          composed: true,
          detail: { message: `No se pudo ejecutar la orden: ${error?.message || error}` },
        })
      );
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const start = this._hass?.states?.[this._config.start_entity];
    const stop = this._hass?.states?.[this._config.stop_entity];
    const active = Boolean(start?.attributes?.active);
    const remaining = start?.attributes?.remaining_time;
    const unavailable =
      !start || !stop || start.state === "unavailable" || stop.state === "unavailable";
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:10px; border-radius:12px; overflow:hidden; }
        .name { margin-bottom:8px; color:var(--primary-text-color); font-size:.92rem;
          font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .runtime { display:flex; align-items:center; gap:5px; min-height:18px;
          margin:-3px 0 7px; color:var(--secondary-text-color); font-size:.72rem; }
        .runtime.active { color:var(--success-color, #2e7d32); font-weight:650; }
        .dot { width:7px; height:7px; border-radius:50%; background:var(--disabled-color); }
        .runtime.active .dot { background:var(--success-color, #2e7d32); }
        .actions { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
        button { min-height:48px; border:1px solid var(--divider-color); border-radius:8px;
          background:var(--card-background-color); color:var(--primary-text-color);
          display:flex; align-items:center; justify-content:center; gap:6px;
          font:inherit; font-size:.76rem; cursor:pointer; }
        button:hover:not(:disabled) { border-color:var(--primary-color); }
        button:disabled { opacity:.45; cursor:default; }
        .start ha-icon { color:var(--success-color, #2e7d32); }
        .stop ha-icon { color:var(--error-color, #d32f2f); }
        ha-icon { --mdc-icon-size:20px; }
      </style>
      <ha-card>
        <div class="name">${this._escape(this._config.name || "Programa")}</div>
        <div class="runtime ${active ? "active" : ""}">
          <span class="dot"></span>
          <span>${
            active
              ? remaining
                ? `En marcha · Restante ${this._escape(remaining)}`
                : "En marcha · Tiempo no disponible"
              : "Detenido"
          }</span>
        </div>
        <div class="actions">
          <button class="start" ${unavailable || this._busy ? "disabled" : ""}>
            <ha-icon icon="mdi:play"></ha-icon><span>Marcha</span>
          </button>
          <button class="stop" ${unavailable || this._busy ? "disabled" : ""}>
            <ha-icon icon="mdi:stop"></ha-icon><span>Paro</span>
          </button>
        </div>
      </ha-card>
    `;
    this.shadowRoot.querySelector(".start")?.addEventListener(
      "click",
      () => this._press(this._config.start_entity, "Marcha")
    );
    this.shadowRoot.querySelector(".stop")?.addEventListener(
      "click",
      () => this._press(this._config.stop_entity, "Paro")
    );
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

class VeggaProgramsGrid extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._signature = "";
  }

  static getStubConfig() {
    return { title: "Control de programas" };
  }

  setConfig(config) {
    this._config = { title: "Control de programas", ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const programs = this._programs();
    const signature = programs
      .map((item) => `${item.start_entity}|${item.stop_entity}`)
      .join(";");
    if (signature !== this._signature || !this.shadowRoot.querySelector(".grid")) {
      this._render(programs);
      return;
    }
    this.shadowRoot.querySelectorAll("vegga-program-card").forEach((card) => {
      card.hass = hass;
    });
  }

  _programs() {
    const pairs = new Map();
    Object.entries(this._hass?.states || {}).forEach(([entityId, stateObj]) => {
      if (!entityId.startsWith("button.")) return;
      const friendlyName = String(stateObj?.attributes?.friendly_name || "");
      const match = friendlyName.match(/(?:^|\s)(Iniciar|Parar) programa (.+)$/i);
      if (!match) return;
      const name = match[2].trim();
      const key = name.toLocaleLowerCase("es");
      const pair = pairs.get(key) || { name };
      pair[match[1].toLocaleLowerCase("es") === "iniciar" ? "start_entity" : "stop_entity"] = entityId;
      pairs.set(key, pair);
    });
    return [...pairs.values()]
      .filter((item) => item.start_entity && item.stop_entity)
      .sort((left, right) =>
        left.name.localeCompare(right.name, "es", { numeric: true, sensitivity: "base" })
      );
  }

  _render(preloadedPrograms = null) {
    if (!this.shadowRoot || !this._hass) return;
    const programs = preloadedPrograms || this._programs();
    this._signature = programs
      .map((item) => `${item.start_entity}|${item.stop_entity}`)
      .join(";");
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:12px; }
        .heading { display:flex; align-items:center; justify-content:space-between;
          gap:12px; padding:6px 4px 16px; }
        h1 { margin:0; color:var(--primary-text-color); font-size:1.55rem; }
        .count { color:var(--secondary-text-color); }
        .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
          gap:8px; align-items:start; }
        .empty { padding:24px; border-radius:14px; color:var(--secondary-text-color);
          background:var(--card-background-color); }
        @media (max-width:430px) {
          :host { padding:6px; }
          .grid { grid-template-columns:1fr; }
          h1 { font-size:1.25rem; }
        }
      </style>
      <div class="heading">
        <h1>${this._escape(this._config.title || "Control de programas")}</h1>
        <span class="count">${programs.length} programas</span>
      </div>
      <div class="grid"></div>
      ${programs.length ? "" : '<div class="empty">No se encontraron controles de programa VEGGA.</div>'}
    `;
    const grid = this.shadowRoot.querySelector(".grid");
    programs.forEach((program) => {
      const card = document.createElement("vegga-program-card");
      card.setConfig(program);
      card.hass = this._hass;
      grid.appendChild(card);
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

if (!customElements.get("vegga-sector-card")) {
  customElements.define("vegga-sector-card", VeggaSectorCard);
}
if (!customElements.get("vegga-sector-card-editor")) {
  customElements.define("vegga-sector-card-editor", VeggaSectorCardEditor);
}
if (!customElements.get("vegga-sectors-grid")) {
  customElements.define("vegga-sectors-grid", VeggaSectorsGrid);
}
if (!customElements.get("vegga-program-card")) {
  customElements.define("vegga-program-card", VeggaProgramCard);
}
if (!customElements.get("vegga-programs-grid")) {
  customElements.define("vegga-programs-grid", VeggaProgramsGrid);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "vegga-sector-card")) {
  window.customCards.push({
    type: "vegga-sector-card",
    name: "VEGGA - Control seguro de sector",
    description: "Cambia el modo de un sector Agrónic con confirmación emergente.",
    preview: true,
    documentationURL: "https://app.veggadigital.com/",
    getEntitySuggestion: (_hass, entityId) =>
      entityId?.startsWith("select.") ? { type: "custom:vegga-sector-card", entity: entityId } : null,
  });
}
if (!window.customCards.some((card) => card.type === "vegga-sectors-grid")) {
  window.customCards.push({
    type: "vegga-sectors-grid",
    name: "VEGGA - Todos los sectores",
    description: "Descubre y muestra todos los controles de sector VEGGA.",
    preview: true,
    documentationURL: "https://app.veggadigital.com/",
  });
}
if (!window.customCards.some((card) => card.type === "vegga-programs-grid")) {
  window.customCards.push({
    type: "vegga-programs-grid",
    name: "VEGGA - Todos los programas",
    description: "Descubre todos los programas VEGGA y muestra Marcha y Paro.",
    preview: true,
    documentationURL: "https://app.veggadigital.com/",
  });
}

console.info(`%c VEGGA SECTOR CARD %c ${CARD_VERSION} `, "background:#1976d2;color:white;font-weight:bold", "background:#eee;color:#333");
