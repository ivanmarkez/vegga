const VEGGA_OVERVIEW_VERSION = "0.5.2";

class VeggaOverviewCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._registry = null;
    this._registryPromise = null;
  }

  static getStubConfig() {
    return { controller: "vivero_agronic_17669", title: "VEGGA" };
  }

  setConfig(config) {
    if (!config?.controller) throw new Error("Debes indicar controller, por ejemplo: vivero_agronic_17669");
    this._config = {
      title: "VEGGA",
      show_irrigation_order: true,
      show_sector_links: true,
      show_programs: true,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 12; }
  getGridOptions() { return { rows: 12, columns: 12, min_rows: 5, min_columns: 6 }; }

  _prefix() { return String(this._config?.controller || "").toLowerCase(); }
  _state(id) { return this._hass?.states?.[id] || null; }
  _allStates() { return Object.values(this._hass?.states || {}); }
  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  }
  _number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  _format(value, decimals = 2) {
    const n = this._number(value);
    return n === null ? "—" : n.toLocaleString("es-ES", { maximumFractionDigits: decimals });
  }
  _validState(state) {
    return state && !["unknown", "unavailable", "none", ""].includes(String(state.state).toLowerCase());
  }
  _friendly(state, fallback = "Sector") {
    return String(state?.attributes?.sector_name || state?.attributes?.friendly_name || fallback)
      .replace(/^Sector\s+/i, "")
      .replace(/\s+(Consumo último riego|Consumo|Último riego|Duración último riego|Programas relacionados)$/i, "")
      .trim();
  }
  _belongsToController(state) {
    const id = state?.entity_id || "";
    return id.split(".")[1]?.startsWith(`${this._prefix()}_`);
  }
  _sectorNumber(state) {
    const n = Number(state?.attributes?.sector_number);
    return Number.isFinite(n) ? n : null;
  }

  _findSectorState(number, predicate) {
    return this._allStates().find(s => this._belongsToController(s) && this._sectorNumber(s) === number && predicate(s)) || null;
  }

  _sectors() {
    const candidates = this._allStates().filter(s =>
      this._belongsToController(s) &&
      this._sectorNumber(s) !== null &&
      Object.prototype.hasOwnProperty.call(s.attributes || {}, "yesterday_volume_m3")
    );

    return candidates.map(consumption => {
      const number = this._sectorNumber(consumption);
      const status = this._findSectorState(number, s => s.entity_id.startsWith("binary_sensor."));
      const last = this._findSectorState(number, s =>
        s.attributes?.started_at !== undefined || s.attributes?.ended_at !== undefined ||
        /ultimo_riego|último_riego/.test(s.entity_id)
      );
      const duration = this._findSectorState(number, s =>
        s.entity_id.startsWith("sensor.") && s.attributes?.unit_of_measurement === "min"
      );
      const programs = this._findSectorState(number, s =>
        Array.isArray(s.attributes?.programs) || s.attributes?.program_count !== undefined
      );
      const select = this._findSectorState(number, s => s.entity_id.startsWith("select."));
      return {
        number,
        name: this._friendly(consumption, `Sector ${number}`),
        consumption,
        status,
        last,
        duration,
        programs,
        linkEntity: select?.entity_id || status?.entity_id || consumption.entity_id,
      };
    }).sort((a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base" }));
  }

  _parseDate(state) {
    if (!this._validState(state)) return null;
    let d = new Date(state.state);
    if (Number.isNaN(d.getTime())) {
      d = new Date(state.attributes?.ended_at || state.attributes?.started_at || state.last_changed);
    }
    return Number.isNaN(d.getTime()) ? null : d;
  }

  _todayIrrigations(sectors) {
    const now = new Date();
    return sectors.map(s => ({ ...s, date: this._parseDate(s.last) }))
      .filter(s => s.date && s.date.getFullYear() === now.getFullYear() && s.date.getMonth() === now.getMonth() && s.date.getDate() === now.getDate())
      .sort((a, b) => a.date - b.date);
  }

  async _loadRegistry() {
    if (this._registry) return this._registry;
    if (this._registryPromise) return this._registryPromise;
    this._registryPromise = this._hass.callWS({ type: "config/entity_registry/list" })
      .then(entries => {
        this._registry = new Map(entries.map(e => [e.entity_id, e]));
        return this._registry;
      })
      .catch(() => new Map());
    return this._registryPromise;
  }

  async _openEntity(entityId) {
    if (!entityId || !this._config.show_sector_links) return;
    try {
      const registry = await this._loadRegistry();
      const deviceId = registry.get(entityId)?.device_id;
      if (deviceId) {
        history.pushState(null, "", `/config/devices/device/${deviceId}`);
        window.dispatchEvent(new Event("location-changed"));
        return;
      }
    } catch (_) {}
    this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
  }

  _delta(today, yesterday) {
    const t = this._number(today), y = this._number(yesterday);
    if (t === null || y === null || y === 0) return { text: "—", cls: "neutral" };
    const d = ((t - y) / y) * 100;
    const cls = Math.abs(d) <= 10 ? "good" : Math.abs(d) <= 20 ? "warn" : "bad";
    return { text: `${d > 0 ? "+" : ""}${Math.round(d)}%`, cls };
  }

  _summaryCard(icon, title, value, subtitle = "") {
    return `<div class="summary"><ha-icon icon="${icon}"></ha-icon><div><div class="summary-title">${this._escape(title)}</div><div class="summary-value">${this._escape(value)}</div>${subtitle ? `<div class="summary-sub">${this._escape(subtitle)}</div>` : ""}</div></div>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const sectors = this._sectors();
    const irrigations = this._todayIrrigations(sectors);
    const prefix = this._prefix();
    const connection = this._state(`binary_sensor.${prefix}_conexion_vegga`);
    const activeSectors = this._state(`sensor.${prefix}_sectores_activos`);
    const activePrograms = this._state(`sensor.${prefix}_programas_activos`);
    const updated = this._state(`sensor.${prefix}_ultima_actualizacion_del_historico`);
    const connected = connection?.state === "on";

    const sectorRows = sectors.map(s => {
      const today = s.consumption?.state;
      const yesterday = s.consumption?.attributes?.yesterday_volume_m3;
      const delta = this._delta(today, yesterday);
      const active = s.status?.state === "on";
      const programs = this._validState(s.programs) ? s.programs.state : "—";
      return `<tr>
        <td><button class="sector-name" data-entity="${this._escape(s.linkEntity)}">${this._escape(s.name)}<ha-icon icon="mdi:chevron-right"></ha-icon></button></td>
        <td class="center"><span class="dot ${active ? "active" : ""}"></span></td>
        <td class="num">${this._format(today)}</td>
        <td class="num">${this._format(yesterday)}</td>
        <td class="num"><span class="delta ${delta.cls}">${delta.text}</span></td>
        ${this._config.show_programs ? `<td class="programs" title="${this._escape(programs)}">${this._escape(programs)}</td>` : ""}
      </tr>`;
    }).join("");

    const irrigationRows = irrigations.map((s, i) => {
      const time = s.date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
      const durationValue = s.duration?.state ?? s.last?.attributes?.duration_minutes;
      const duration = this._number(durationValue) === null ? "—" : `${this._format(durationValue, 0)} min`;
      const volume = s.last?.attributes?.volume_m3 ?? s.consumption?.state;
      return `<tr><td class="order">${i + 1}.º</td><td><button class="sector-name" data-entity="${this._escape(s.linkEntity)}">${this._escape(s.name)}<ha-icon icon="mdi:chevron-right"></ha-icon></button></td><td class="center">${time}</td><td class="num">${duration}</td><td class="num">${this._format(volume)} m³</td></tr>`;
    }).join("");

    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{overflow:hidden}.wrap{padding:18px}.titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.titlebar h2{margin:0;font-size:1.35rem}.version{color:var(--secondary-text-color);font-size:.75rem}.summaries{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}.summary{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color)}.summary ha-icon{--mdc-icon-size:29px;color:var(--primary-color)}.summary-title{font-weight:650}.summary-value{font-size:.95rem;margin-top:2px}.summary-sub{font-size:.76rem;color:var(--secondary-text-color);margin-top:2px}.section{margin-top:18px}.section h3{margin:0 0 10px;font-size:1.05rem}.table-wrap{overflow:auto;border:1px solid var(--divider-color);border-radius:12px}table{width:100%;border-collapse:collapse;min-width:680px}th,td{padding:9px 10px;border-bottom:1px solid var(--divider-color);text-align:left}th{background:var(--secondary-background-color);position:sticky;top:0;z-index:1;font-size:.82rem}tr:last-child td{border-bottom:0}.num{text-align:right;white-space:nowrap}.center{text-align:center}.sector-name{border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:650;cursor:pointer;padding:0;display:inline-flex;align-items:center;gap:3px;text-align:left}.sector-name:hover{color:var(--primary-color);text-decoration:underline}.sector-name ha-icon{--mdc-icon-size:16px}.dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#b39ddb)}.dot.active{background:var(--success-color,#2e7d32);box-shadow:0 0 0 4px color-mix(in srgb,var(--success-color,#2e7d32) 20%,transparent)}.delta{display:inline-flex;align-items:center;gap:4px}.delta:before{content:"";width:10px;height:10px;border-radius:50%;background:var(--secondary-text-color)}.delta.good:before{background:var(--success-color,#2e7d32)}.delta.warn:before{background:var(--warning-color,#f9a825)}.delta.bad:before{background:var(--error-color,#d32f2f)}.programs{max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.order{font-weight:800;text-align:center}.empty{padding:18px;color:var(--secondary-text-color);text-align:center}
      @media(max-width:899px){.wrap{padding:12px}.summaries{grid-template-columns:repeat(2,minmax(0,1fr))}.summary{padding:11px}.programs{display:none}table{min-width:520px}.titlebar h2{font-size:1.15rem}}
      @media(max-width:480px){.summaries{grid-template-columns:1fr 1fr;gap:7px}.summary ha-icon{--mdc-icon-size:23px}.summary-title{font-size:.82rem}.summary-value{font-size:.82rem}}
    </style><ha-card><div class="wrap">
      <div class="titlebar"><h2>${this._escape(this._config.title)}</h2><span class="version">VEGGA ${VEGGA_OVERVIEW_VERSION}</span></div>
      <div class="summaries">
        ${this._summaryCard("mdi:monitor-dashboard", "VEGGA", connected ? "Conectado" : "Desconectado", connection?.attributes?.friendly_name || "")}
        ${this._summaryCard("mdi:pipe-valve", "Sectores activos", activeSectors?.state ?? "—", `${sectors.length} sectores`)}
        ${this._summaryCard("mdi:water-pump", "Programas activos", activePrograms?.state ?? "—")}
        ${this._summaryCard("mdi:database-sync", "Actualización", updated?.state ?? "—")}
      </div>
      ${this._config.show_irrigation_order ? `<div class="section"><h3>Orden de riego de hoy</h3><div class="table-wrap">${irrigations.length ? `<table><thead><tr><th>Orden</th><th>Sector</th><th>Hora</th><th>Duración</th><th>Consumo</th></tr></thead><tbody>${irrigationRows}</tbody></table>` : `<div class="empty">Todavía no hay riegos registrados hoy.</div>`}</div></div>` : ""}
      <div class="section"><h3>Sectores</h3><div class="table-wrap">${sectors.length ? `<table><thead><tr><th>Sector</th><th>Estado</th><th>Hoy</th><th>Ayer</th><th>Δ</th>${this._config.show_programs ? `<th>Programas relacionados</th>` : ""}</tr></thead><tbody>${sectorRows}</tbody></table>` : `<div class="empty">No se han encontrado sectores para el controlador indicado.</div>`}</div></div>
    </div></ha-card>`;

    this.shadowRoot.querySelectorAll("button[data-entity]").forEach(btn => btn.addEventListener("click", () => this._openEntity(btn.dataset.entity)));
  }
}

if (!customElements.get("vegga-overview-card")) customElements.define("vegga-overview-card", VeggaOverviewCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === "vegga-overview-card")) {
  window.customCards.push({ type: "vegga-overview-card", name: "VEGGA - Vista general", description: "Vista completa con sectores, programas y orden real de riego." });
}
console.info(`%c VEGGA overview card ${VEGGA_OVERVIEW_VERSION} `, "color:white;background:#00897b;font-weight:bold;padding:3px 6px;border-radius:4px");
