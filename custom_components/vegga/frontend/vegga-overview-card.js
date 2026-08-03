const VEGGA_UI_VERSION = "0.5.9";
const VEGGA_SECTOR_MODES = [
  { value: "Automático", short: "Auto", icon: "mdi:autorenew", cls: "auto" },
  { value: "Marcha manual", short: "Marcha", icon: "mdi:play", cls: "start" },
  { value: "Paro manual", short: "Paro", icon: "mdi:stop", cls: "stop" },
];

const VeggaUi = {
  escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[char]));
  },
  prefix(config) {
    return String(config?.controller || "").toLowerCase();
  },
  controllerDeviceId(hass, config) {
    const prefix = this.prefix(config);
    const controllerState = hass?.states?.[`sensor.${prefix}_sectores`]
      || hass?.states?.[`sensor.${prefix}_programas`]
      || hass?.states?.[`binary_sensor.${prefix}_conexion_vegga`];
    const explicit = controllerState?.attributes?.device_id
      ?? controllerState?.attributes?.vegga_device_id;
    if (explicit !== undefined && explicit !== null && String(explicit).trim()) {
      return String(explicit).trim();
    }
    const trailingNumber = prefix.match(/(?:^|_)(\d+)$/);
    return trailingNumber ? trailingNumber[1] : "";
  },
  belongs(state, config, hass) {
    const configuredDevice = this.controllerDeviceId(hass, config);
    const stateDevice = state?.attributes?.vegga_device_id
      ?? state?.attributes?.device_id;
    if (configuredDevice && stateDevice !== undefined && stateDevice !== null) {
      return String(stateDevice) === configuredDevice;
    }
    const stem = String(state?.entity_id || "").split(".")[1] || "";
    return stem.startsWith(`${this.prefix(config)}_`);
  },
  number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  },
  notify(host, message) {
    host.dispatchEvent(new CustomEvent("hass-notification", {
      bubbles: true,
      composed: true,
      detail: { message },
    }));
  },
  moreInfo(host, entityId) {
    host.dispatchEvent(new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    }));
  },
};

class VeggaOverviewCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._registry = null;
    this._registryPromise = null;
    this._actualHistory = new Map();
    this._actualHistoryKey = "";
    this._actualHistoryPromise = null;
    this._actualHistoryError = null;
  }

  static getStubConfig() {
    return { controller: "vivero_agronic_17669", title: "VEGGA" };
  }

  setConfig(config) {
    if (!config?.controller) throw new Error("Debes indicar controller, por ejemplo: vivero_agronic_17669");
    this._config = {
      title: "Resumen de riego",
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
    this._scheduleActualHistory();
  }

  getCardSize() { return 12; }
  getGridOptions() { return { rows: 12, columns: 12, min_rows: 5, min_columns: 6 }; }

  _prefix() { return VeggaUi.prefix(this._config); }
  _state(id) { return this._hass?.states?.[id] || null; }
  _allStates() { return Object.values(this._hass?.states || {}); }
  _escape(value) { return VeggaUi.escape(value); }
  _number(value) { return VeggaUi.number(value); }
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
  _belongsToController(state) { return VeggaUi.belongs(state, this._config, this._hass); }
  _sectorNumber(state) {
    const n = Number(state?.attributes?.sector_number);
    return Number.isFinite(n) ? n : null;
  }

  _findSectorState(number, predicate) {
    const matches = this._allStates().filter((state) =>
      this._sectorNumber(state) === number && predicate(state)
    );
    const owned = matches.find((state) => this._belongsToController(state));
    if (owned) return owned;
    // Older entity ids created by Home Assistant may not contain the controller
    // prefix. When there is only one unambiguous sector entity, use it.
    return matches.length === 1 ? matches[0] : null;
  }

  _sectors() {
    const candidates = this._allStates().filter((state) =>
      this._belongsToController(state) &&
      this._sectorNumber(state) !== null &&
      Object.prototype.hasOwnProperty.call(state.attributes || {}, "yesterday_volume_m3")
    );

    return candidates.map((consumption) => {
      const number = this._sectorNumber(consumption);
      const status = this._findSectorState(number, (state) =>
        state.entity_id.startsWith("binary_sensor.") &&
        (state.attributes?.device_class === "running" || /riego_activo/.test(state.entity_id) || /Riego activo$/i.test(state.attributes?.friendly_name || ""))
      );
      const last = this._findSectorState(number, (state) =>
        state.attributes?.started_at !== undefined || state.attributes?.ended_at !== undefined ||
        /ultimo_riego|último_riego/.test(state.entity_id)
      );
      const duration = this._findSectorState(number, (state) =>
        state.entity_id.startsWith("sensor.") && state.attributes?.unit_of_measurement === "min"
      );
      const programs = this._findSectorState(number, (state) =>
        Array.isArray(state.attributes?.programs) || state.attributes?.program_count !== undefined
      );
      const select = this._findSectorState(number, (state) => state.entity_id.startsWith("select."));
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

  _date(value) {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  _sameLocalDay(a, b = new Date()) {
    return Boolean(a) && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  _clock(value) {
    const date = this._date(value);
    return date ? date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "—";
  }

  _actualMoment(value) {
    const date = this._date(value);
    if (!date) return "—";
    const time = this._clock(date);
    return this._sameLocalDay(date)
      ? time
      : `${date.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" })} · ${time}`;
  }

  _actualTimes(sector) {
    const observed = sector.status?.entity_id
      ? this._actualHistory.get(sector.status.entity_id)
      : null;
    if (observed?.hasActivity) {
      return {
        started: observed.started,
        ended: observed.active ? null : observed.ended,
        active: observed.active,
        durationMinutes: observed.durationMinutes,
        source: "home_assistant_history",
      };
    }

    const attrs = sector.last?.attributes || {};
    const consumptionAttrs = sector.consumption?.attributes || {};
    let started = this._date(attrs.started_at || consumptionAttrs.last_started_at);
    let ended = this._date(attrs.ended_at || consumptionAttrs.last_ended_at);
    const active = sector.status?.state === "on";
    const durationValue = sector.duration?.state ?? attrs.duration_minutes ?? consumptionAttrs.last_duration_minutes;
    const durationMinutes = this._number(durationValue);

    if (active) {
      const stateStarted = this._date(sector.status?.last_changed);
      if (stateStarted && (!started || stateStarted > started)) started = stateStarted;
      ended = null;
    }

    return { started, ended, active, durationMinutes, source: "vegga_summary" };
  }

  _historyRowState(row) {
    return String(row?.state ?? row?.s ?? "").toLowerCase();
  }

  _historyRowDate(row) {
    const value = row?.last_changed ?? row?.last_updated ?? row?.lc ?? row?.lu;
    if (typeof value === "number") {
      const millis = value > 100000000000 ? value : value * 1000;
      const date = new Date(millis);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    return this._date(value);
  }

  _historyRowsForEntity(response, entityId) {
    if (!response) return [];
    if (!Array.isArray(response) && typeof response === "object") {
      const direct = response[entityId];
      if (Array.isArray(direct)) return direct;
      if (Array.isArray(response.states?.[entityId])) return response.states[entityId];
    }
    if (Array.isArray(response)) {
      if (response.length && Array.isArray(response[0])) {
        const matching = response.find((rows) => rows?.some?.((row) => row?.entity_id === entityId));
        return Array.isArray(matching) ? matching : [];
      }
      return response.filter((row) => row?.entity_id === entityId);
    }
    return [];
  }

  _deriveObservedWindow(rows, currentState, dayStart, now) {
    const sorted = [...rows]
      .map((row) => ({ row, at: this._historyRowDate(row) }))
      .filter((item) => item.at)
      .sort((a, b) => a.at - b.at);

    let previousOn = false;
    let activeSince = null;
    let firstStart = null;
    let lastEnd = null;
    let totalMs = 0;
    let sawActivity = false;

    for (const { row, at } of sorted) {
      const isOn = this._historyRowState(row) === "on";
      const time = new Date(Math.max(dayStart.getTime(), at.getTime()));
      if (isOn && !previousOn) {
        activeSince = time;
        if (!firstStart) firstStart = time;
        sawActivity = true;
      } else if (!isOn && previousOn) {
        if (activeSince) totalMs += Math.max(0, time.getTime() - activeSince.getTime());
        lastEnd = time;
        activeSince = null;
      }
      previousOn = isOn;
    }

    const currentlyOn = String(currentState?.state || "").toLowerCase() === "on";
    if (currentlyOn && !activeSince) {
      const changed = this._date(currentState?.last_changed);
      activeSince = changed && changed >= dayStart ? changed : dayStart;
      if (!firstStart) firstStart = activeSince;
      sawActivity = true;
    }
    if (currentlyOn && activeSince) {
      totalMs += Math.max(0, now.getTime() - activeSince.getTime());
    } else if (!currentlyOn && previousOn && activeSince) {
      totalMs += Math.max(0, now.getTime() - activeSince.getTime());
      lastEnd = now;
      activeSince = null;
    }

    return {
      hasActivity: sawActivity,
      started: firstStart,
      ended: lastEnd,
      active: currentlyOn,
      durationMinutes: sawActivity ? Math.max(0, Math.round(totalMs / 60000)) : null,
    };
  }

  _localDayKey(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  _scheduleActualHistory() {
    if (!this._hass || !this._config || typeof this._hass.callWS !== "function") return;
    const sectors = this._sectors();
    const statuses = sectors.map((sector) => sector.status).filter(Boolean);
    if (!statuses.length) return;
    const ids = [...new Set(statuses.map((state) => state.entity_id))].sort();
    const stateSignature = ids.map((entityId) => {
      const state = this._state(entityId);
      return `${entityId}:${state?.state || ""}:${state?.last_changed || ""}`;
    }).join("|");
    const key = `${this._localDayKey()}|${stateSignature}`;
    if (this._actualHistoryKey === key && (this._actualHistory.size || this._actualHistoryPromise)) return;
    this._actualHistoryKey = key;
    this._actualHistoryPromise = this._loadActualHistory(ids, key);
  }

  async _loadActualHistory(entityIds, key) {
    const now = new Date();
    const dayStart = new Date(now);
    dayStart.setHours(0, 0, 0, 0);
    try {
      const response = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: dayStart.toISOString(),
        end_time: now.toISOString(),
        entity_ids: entityIds,
        minimal_response: false,
        no_attributes: true,
        significant_changes_only: false,
      });
      if (this._actualHistoryKey !== key) return;
      const next = new Map();
      for (const entityId of entityIds) {
        const rows = this._historyRowsForEntity(response, entityId);
        next.set(entityId, this._deriveObservedWindow(rows, this._state(entityId), dayStart, now));
      }
      this._actualHistory = next;
      this._actualHistoryError = null;
    } catch (error) {
      if (this._actualHistoryKey !== key) return;
      this._actualHistoryError = String(error?.message || error || "No se pudo leer el histórico de Home Assistant");
    } finally {
      if (this._actualHistoryKey === key) this._actualHistoryPromise = null;
      this._render();
    }
  }

  _todayIrrigations(sectors) {
    const now = new Date();
    return sectors
      .map((sector) => ({ ...sector, actual: this._actualTimes(sector) }))
      .filter((sector) => this._sameLocalDay(sector.actual.started, now) || this._sameLocalDay(sector.actual.ended, now))
      .sort((a, b) => (a.actual.started || a.actual.ended) - (b.actual.started || b.actual.ended));
  }

  async _loadRegistry() {
    if (this._registry) return this._registry;
    if (this._registryPromise) return this._registryPromise;
    this._registryPromise = this._hass.callWS({ type: "config/entity_registry/list" })
      .then((entries) => {
        this._registry = new Map(entries.map((entry) => [entry.entity_id, entry]));
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
    } catch (_) {
      // Fall back to more-info below.
    }
    VeggaUi.moreInfo(this, entityId);
  }

  _delta(today, yesterday) {
    const current = this._number(today);
    const previous = this._number(yesterday);
    if (current === null || previous === null || previous === 0) return { text: "—", cls: "neutral" };
    const delta = ((current - previous) / previous) * 100;
    const cls = Math.abs(delta) <= 10 ? "good" : Math.abs(delta) <= 20 ? "warn" : "bad";
    return { text: `${delta > 0 ? "+" : ""}${Math.round(delta)}%`, cls };
  }

  _summaryCard(icon, title, value, subtitle = "") {
    return `<div class="summary"><ha-icon icon="${icon}"></ha-icon><div><div class="summary-title">${this._escape(title)}</div><div class="summary-value">${this._escape(value)}</div>${subtitle ? `<div class="summary-sub">${this._escape(subtitle)}</div>` : ""}</div></div>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const sectors = this._sectors();
    const irrigations = this._todayIrrigations(sectors);
    const todayOrder = new Map(irrigations.map((sector, index) => [sector.number, index + 1]));
    const orderedSectors = [...sectors].sort((a, b) => {
      const aOrder = todayOrder.get(a.number);
      const bOrder = todayOrder.get(b.number);
      if (aOrder && bOrder) return aOrder - bOrder;
      if (aOrder) return -1;
      if (bOrder) return 1;
      return a.name.localeCompare(b.name, "es", { sensitivity: "base", numeric: true });
    });

    const prefix = this._prefix();
    const connection = this._state(`binary_sensor.${prefix}_conexion_vegga`);
    const activeSectors = this._state(`sensor.${prefix}_sectores_activos`);
    const activePrograms = this._state(`sensor.${prefix}_programas_activos`);
    const updated = this._state(`sensor.${prefix}_ultima_actualizacion_del_historico`);
    const connected = connection?.state === "on";

    const viewModel = orderedSectors.map((sector) => {
      const today = sector.consumption?.state;
      const yesterday = sector.consumption?.attributes?.yesterday_volume_m3;
      const delta = this._delta(today, yesterday);
      const actual = this._actualTimes(sector);
      const durationValue = actual.durationMinutes
        ?? sector.duration?.state
        ?? sector.last?.attributes?.duration_minutes
        ?? sector.consumption?.attributes?.last_duration_minutes;
      const durationNumber = this._number(durationValue);
      const duration = durationNumber === null ? "—" : `${this._format(durationNumber, 0)} min`;
      let programs = this._validState(sector.programs) ? sector.programs.state : "—";
      if (programs === "—") {
        const programName = sector.consumption?.attributes?.program_name;
        const programNumber = sector.consumption?.attributes?.program_number;
        if (programName) programs = String(programName);
        else if (programNumber !== undefined && programNumber !== null) programs = `Programa ${programNumber}`;
      }
      const hasPrograms = !["—", "Sin programa relacionado"].includes(String(programs));
      const order = todayOrder.get(sector.number) || null;
      const startedTitle = actual.started ? actual.started.toLocaleString("es-ES") : "Sin inicio real registrado";
      const endedTitle = actual.active ? "El sector continúa regando" : actual.ended ? actual.ended.toLocaleString("es-ES") : "Sin fin real registrado";
      return {
        sector, today, yesterday, delta, actual, duration, programs, hasPrograms, order,
        startedTitle, endedTitle,
      };
    });

    const desktopRows = viewModel.map((item) => `<tr class="${item.order ? "today-row" : ""}">
      ${this._config.show_irrigation_order !== false ? `<td class="order">${item.order ? `${item.order}.º` : "—"}</td>` : ""}
      <td><button class="sector-name" data-entity="${this._escape(item.sector.linkEntity)}">${this._escape(item.sector.name)}<ha-icon icon="mdi:chevron-right"></ha-icon></button></td>
      <td class="center"><span class="dot ${item.actual.active ? "active" : ""}"></span></td>
      <td class="time" title="${this._escape(item.startedTitle)}">${this._escape(this._actualMoment(item.actual.started))}</td>
      <td class="time ${item.actual.active ? "running" : ""}" title="${this._escape(item.endedTitle)}">${item.actual.active ? "En curso" : this._escape(this._actualMoment(item.actual.ended))}</td>
      <td class="num">${this._escape(item.duration)}</td>
      <td class="num">${this._format(item.today)}</td>
      <td class="num">${this._format(item.yesterday)}</td>
      <td class="num"><span class="delta ${item.delta.cls}">${item.delta.text}</span></td>
      ${this._config.show_programs ? `<td class="programs" title="${this._escape(item.programs)}">${this._escape(item.programs)}</td>` : ""}
    </tr>`).join("");

    const mobileCards = viewModel.map((item) => `<article class="sector-mobile ${item.order ? "today" : ""}">
      <div class="mobile-head">
        <button class="sector-name mobile-name" data-entity="${this._escape(item.sector.linkEntity)}">${this._escape(item.sector.name)}<ha-icon icon="mdi:chevron-right"></ha-icon></button>
        <span class="state-pill ${item.actual.active ? "active" : ""}"><span class="dot ${item.actual.active ? "active" : ""}"></span>${item.actual.active ? "Regando" : "Parado"}</span>
      </div>
      ${item.order ? `<div class="today-badge"><ha-icon icon="mdi:clock-check-outline"></ha-icon>Riego de hoy · ${item.order}.º</div>` : ""}
      <div class="mobile-grid">
        <div class="metric"><span>Inicio real</span><strong>${this._escape(this._actualMoment(item.actual.started))}</strong></div>
        <div class="metric"><span>Fin real</span><strong class="${item.actual.active ? "running" : ""}">${item.actual.active ? "En curso" : this._escape(this._actualMoment(item.actual.ended))}</strong></div>
        <div class="metric"><span>Duración</span><strong>${this._escape(item.duration)}</strong></div>
        <div class="metric"><span>Hoy</span><strong>${this._format(item.today)} m³</strong></div>
        <div class="metric"><span>Ayer</span><strong>${this._format(item.yesterday)} m³</strong></div>
        <div class="metric"><span>Diferencia</span><strong><span class="delta ${item.delta.cls}">${item.delta.text}</span></strong></div>
      </div>
      ${this._config.show_programs && item.hasPrograms ? `<div class="mobile-programs"><span>Programas</span><strong>${this._escape(item.programs)}</strong></div>` : ""}
    </article>`).join("");

    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{overflow:hidden}.wrap{padding:18px}.titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.titlebar h2{margin:0;font-size:1.35rem}.version{color:var(--secondary-text-color);font-size:.75rem}.summaries{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}.summary{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color)}.summary ha-icon{--mdc-icon-size:29px;color:var(--primary-color)}.summary-title{font-weight:650}.summary-value{font-size:.95rem;margin-top:2px}.summary-sub{font-size:.76rem;color:var(--secondary-text-color);margin-top:2px}.section{margin-top:18px}.section-title{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:10px}.section-title h3{margin:0;font-size:1.05rem}.section-note{font-size:.78rem;color:var(--secondary-text-color);text-align:right}.table-wrap{overflow:auto;border:1px solid var(--divider-color);border-radius:12px}.desktop-table{width:100%;border-collapse:collapse;min-width:1050px}.desktop-table th,.desktop-table td{padding:9px 10px;border-bottom:1px solid var(--divider-color);text-align:left}.desktop-table th{background:var(--secondary-background-color);position:sticky;top:0;z-index:1;font-size:.82rem}.desktop-table tr:last-child td{border-bottom:0}.desktop-table .today-row{background:color-mix(in srgb,var(--primary-color) 4%,transparent)}.num{text-align:right!important;white-space:nowrap}.center{text-align:center!important}.time{text-align:center!important;white-space:nowrap;font-variant-numeric:tabular-nums}.running{color:var(--success-color,#2e7d32)!important;font-weight:700}.sector-name{border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:650;cursor:pointer;padding:0;display:inline-flex;align-items:center;gap:3px;text-align:left}.sector-name:hover{color:var(--primary-color);text-decoration:underline}.sector-name ha-icon{--mdc-icon-size:16px}.dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#b39ddb);flex:0 0 auto}.dot.active{background:var(--success-color,#2e7d32);box-shadow:0 0 0 4px color-mix(in srgb,var(--success-color,#2e7d32) 20%,transparent)}.delta{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.delta:before{content:"";width:10px;height:10px;border-radius:50%;background:var(--secondary-text-color);flex:0 0 auto}.delta.good:before{background:var(--success-color,#2e7d32)}.delta.warn:before{background:var(--warning-color,#f9a825)}.delta.bad:before{background:var(--error-color,#d32f2f)}.programs{max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.order{font-weight:800;text-align:center!important;white-space:nowrap}.empty{padding:18px;color:var(--secondary-text-color);text-align:center}.mobile-list{display:none}
      @media(max-width:899px){.wrap{padding:12px}.summaries{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.summary{padding:11px;min-width:0}.summary>div{min-width:0}.summary-value,.summary-sub{overflow:hidden;text-overflow:ellipsis}.section-title{align-items:flex-start;flex-direction:column;gap:3px}.section-note{text-align:left}.desktop-only{display:none}.mobile-list{display:grid;gap:10px}.sector-mobile{border:1px solid var(--divider-color);border-radius:14px;padding:13px;background:var(--card-background-color);min-width:0}.sector-mobile.today{border-left:4px solid var(--primary-color);padding-left:10px}.mobile-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.mobile-name{font-size:1rem;min-width:0;overflow-wrap:anywhere}.state-pill{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;border-radius:999px;padding:5px 9px;background:var(--secondary-background-color);color:var(--secondary-text-color);font-size:.76rem;font-weight:700}.state-pill .dot{width:9px;height:9px}.state-pill.active{color:var(--success-color,#2e7d32);background:color-mix(in srgb,var(--success-color,#2e7d32) 14%,var(--card-background-color))}.today-badge{display:inline-flex;align-items:center;gap:5px;margin-top:9px;padding:5px 8px;border-radius:8px;background:color-mix(in srgb,var(--primary-color) 11%,var(--card-background-color));color:var(--primary-color);font-size:.76rem;font-weight:700}.today-badge ha-icon{--mdc-icon-size:16px}.mobile-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin-top:11px;border:1px solid var(--divider-color);border-radius:11px;overflow:hidden;background:var(--divider-color)}.metric{display:flex;flex-direction:column;gap:3px;min-width:0;padding:10px;background:var(--card-background-color)}.metric span:first-child,.mobile-programs>span{font-size:.72rem;color:var(--secondary-text-color)}.metric strong{font-size:.9rem;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.mobile-programs{display:flex;flex-direction:column;gap:3px;margin-top:10px;padding:9px 10px;border-radius:10px;background:var(--secondary-background-color);min-width:0}.mobile-programs strong{font-size:.82rem;overflow-wrap:anywhere}.titlebar h2{font-size:1.15rem}}
      @media(max-width:480px){.summary ha-icon{--mdc-icon-size:23px}.summary-title{font-size:.8rem}.summary-value{font-size:.8rem}.summary-sub{font-size:.68rem}.metric{padding:9px 8px}.metric strong{font-size:.84rem}.state-pill{font-size:.7rem;padding:5px 7px}}
    </style><ha-card><div class="wrap">
      <div class="titlebar"><h2>${this._escape(this._config.title)}</h2><span class="version">VEGGA ${VEGGA_UI_VERSION}</span></div>
      <div class="summaries">
        ${this._summaryCard("mdi:monitor-dashboard", "VEGGA", connected ? "Conectado" : "Desconectado", connection?.attributes?.friendly_name || "")}
        ${this._summaryCard("mdi:pipe-valve", "Sectores activos", activeSectors?.state ?? "—", `${sectors.length} sectores`)}
        ${this._summaryCard("mdi:water-pump", "Programas activos", activePrograms?.state ?? "—")}
        ${this._summaryCard("mdi:database-sync", "Actualización", updated?.state ?? "—")}
      </div>
      <div class="section">
        <div class="section-title"><h3>Riegos por sector</h3><div class="section-note">Los riegos de hoy aparecen primero y en su orden real de inicio.</div></div>
        ${sectors.length ? `<div class="table-wrap desktop-only"><table class="desktop-table"><thead><tr>${this._config.show_irrigation_order !== false ? "<th>Orden hoy</th>" : ""}<th>Sector</th><th>Estado</th><th>Inicio real</th><th>Fin real</th><th>Duración</th><th>Hoy</th><th>Ayer</th><th>Δ</th>${this._config.show_programs ? '<th class="programs">Programas relacionados</th>' : ""}</tr></thead><tbody>${desktopRows}</tbody></table></div><div class="mobile-list">${mobileCards}</div>` : `<div class="empty">No se han encontrado sectores para el controlador indicado.</div>`}
      </div>
    </div></ha-card>`;

    this.shadowRoot.querySelectorAll("button[data-entity]").forEach((button) => {
      button.addEventListener("click", () => this._openEntity(button.dataset.entity));
    });
  }
}

class VeggaSectorControlsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._pending = null;
    this._busy = false;
    this._message = "";
  }

  static getStubConfig() {
    return { controller: "vivero_agronic_17669", title: "Control de sectores" };
  }

  setConfig(config) {
    if (!config?.controller) throw new Error("Debes indicar controller.");
    this._config = { title: "Control de sectores", confirm: true, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._scheduleActualHistory();
  }

  getCardSize() { return 12; }
  getGridOptions() { return { rows: 12, columns: 12, min_rows: 5, min_columns: 6 }; }

  _sectorName(state) {
    const explicit = state?.attributes?.sector_name;
    if (explicit !== undefined && explicit !== null && String(explicit).trim()) {
      return String(explicit).trim();
    }
    return String(state?.attributes?.friendly_name || state?.entity_id || "Sector")
      .replace(/^Sector\s+/i, "")
      .replace(/\s+Modo de funcionamiento$/i, "")
      .trim();
  }

  _selects() {
    return Object.values(this._hass?.states || {})
      .filter((state) => {
        if (!state.entity_id.startsWith("select.")) return false;
        const options = Array.isArray(state.attributes?.options) ? state.attributes.options : [];
        const isSectorMode = state.attributes?.vegga_entity_type === "sector_mode"
          || VEGGA_SECTOR_MODES.every((mode) => options.includes(mode.value));
        if (!isSectorMode) return false;
        if (state.attributes?.vegga_device_id !== undefined) {
          return VeggaUi.belongs(state, this._config, this._hass);
        }
        // Compatibility with entities created by older VEGGA versions.  Their
        // entity_id is based on the sector device name, not the controller.
        return true;
      })
      .map((state) => ({ state, name: this._sectorName(state) }))
      .sort((a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base", numeric: true }));
  }

  _ask(entityId, option, name, current) {
    if (this._busy || current === option) return;
    this._pending = { entityId, option, name, current };
    this._message = "";
    this._render();
    const dialog = this.shadowRoot.querySelector("dialog");
    if (this._config.confirm === false) this._apply();
    else if (dialog && !dialog.open) dialog.showModal();
  }

  _close() {
    if (this._busy) return;
    this.shadowRoot.querySelector("dialog")?.close();
    this._pending = null;
    this._message = "";
    this._render();
  }

  async _apply() {
    if (!this._hass || !this._pending || this._busy) return;
    this._busy = true;
    this._message = "Enviando orden al Agrónic…";
    this._render();
    this.shadowRoot.querySelector("dialog")?.showModal();
    const pending = this._pending;
    try {
      await this._hass.callService("select", "select_option", {
        entity_id: pending.entityId,
        option: pending.option,
      });
      this._busy = false;
      this._pending = null;
      this._message = "";
      this._render();
      VeggaUi.notify(this, `${pending.name}: ${pending.option}`);
    } catch (error) {
      this._busy = false;
      this._message = `No se pudo enviar la orden: ${error?.message || error}`;
      this._render();
      this.shadowRoot.querySelector("dialog")?.showModal();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const sectors = this._selects();
    const rows = sectors.map(({ state, name }) => {
      const available = !["unknown", "unavailable", "none", ""].includes(String(state.state).toLowerCase());
      return `<div class="sector-row">
        <div class="sector-info">
          <button class="name" data-info="${VeggaUi.escape(state.entity_id)}">${VeggaUi.escape(name)}<ha-icon icon="mdi:information-outline"></ha-icon></button>
          <span class="current">Actual: <strong>${VeggaUi.escape(state.state)}</strong></span>
        </div>
        <div class="modes">
          ${VEGGA_SECTOR_MODES.map((mode) => `<button class="mode ${mode.cls} ${state.state === mode.value ? "selected" : ""}" data-entity="${VeggaUi.escape(state.entity_id)}" data-option="${VeggaUi.escape(mode.value)}" data-name="${VeggaUi.escape(name)}" data-current="${VeggaUi.escape(state.state)}" ${!available || this._busy || state.state === mode.value ? "disabled" : ""}>
            <ha-icon icon="${mode.icon}"></ha-icon><span>${mode.short}</span>
          </button>`).join("")}
        </div>
      </div>`;
    }).join("");

    const pending = this._pending;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{overflow:hidden}.wrap{padding:18px}.titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.titlebar h2{margin:0;font-size:1.35rem}.count{color:var(--secondary-text-color);font-size:.82rem}.list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.sector-row{display:grid;grid-template-columns:minmax(160px,1fr) minmax(280px,1.35fr);align-items:center;gap:12px;padding:12px;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color)}.sector-info{min-width:0;display:flex;flex-direction:column;gap:4px}.name{border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:700;text-align:left;padding:0;cursor:pointer;display:flex;align-items:center;gap:5px;min-width:0}.name:hover{color:var(--primary-color)}.name ha-icon{--mdc-icon-size:16px;color:var(--secondary-text-color)}.current{font-size:.78rem;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.modes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.mode{min-height:48px;border:1px solid var(--divider-color);border-radius:11px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit;font-size:.8rem;font-weight:650;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:5px;padding:6px}.mode:hover:not(:disabled){border-color:var(--primary-color);transform:translateY(-1px)}.mode:disabled{cursor:default;opacity:.52}.mode.selected{border:2px solid var(--primary-color);background:color-mix(in srgb,var(--primary-color) 12%,var(--card-background-color));opacity:1}.mode ha-icon{--mdc-icon-size:20px}.auto ha-icon{color:var(--primary-color)}.start ha-icon{color:var(--success-color,#2e7d32)}.stop ha-icon{color:var(--error-color,#d32f2f)}.empty{padding:22px;text-align:center;color:var(--secondary-text-color);border:1px solid var(--divider-color);border-radius:14px}dialog{width:min(460px,calc(100vw - 28px));border:0;border-radius:18px;padding:0;color:var(--primary-text-color);background:var(--card-background-color);box-shadow:0 14px 44px rgba(0,0,0,.4)}dialog::backdrop{background:rgba(0,0,0,.58)}.dialog-body{padding:24px}.dialog-title{font-size:1.18rem;font-weight:750;display:flex;align-items:center;gap:9px}.dialog-title ha-icon{color:var(--warning-color,#f9a825)}.change{margin:17px 0;padding:14px;border-radius:12px;background:var(--secondary-background-color);line-height:1.5}.message{font-size:.9rem;color:var(--primary-color);margin-top:12px}.message.error{color:var(--error-color)}.dialog-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.dialog-actions button{min-height:42px;border-radius:10px;padding:0 16px;font:inherit;font-weight:700;cursor:pointer}.cancel{border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color)}.confirm{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff)}
      @media(max-width:1100px){.list{grid-template-columns:1fr}}
      @media(max-width:600px){.wrap{padding:12px}.sector-row{grid-template-columns:1fr;gap:9px}.modes{gap:5px}.mode{min-height:50px;padding:4px;font-size:.76rem}.titlebar h2{font-size:1.15rem}}
    </style><ha-card><div class="wrap">
      <div class="titlebar"><h2>${VeggaUi.escape(this._config.title)}</h2><span class="count">${sectors.length} sectores</span></div>
      ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">No se han encontrado los selectores de modo de los sectores.</div>`}
    </div></ha-card>
    <dialog><div class="dialog-body">
      <div class="dialog-title"><ha-icon icon="mdi:shield-alert"></ha-icon>Confirmar orden de sector</div>
      ${pending ? `<div class="change"><strong>${VeggaUi.escape(pending.name)}</strong><br>${VeggaUi.escape(pending.current)} → <strong>${VeggaUi.escape(pending.option)}</strong></div><div>La orden se enviará inmediatamente al programador Agrónic.</div>` : ""}
      ${this._message ? `<div class="message ${this._message.startsWith("No se pudo") ? "error" : ""}">${VeggaUi.escape(this._message)}</div>` : ""}
      <div class="dialog-actions"><button class="cancel" ${this._busy ? "disabled" : ""}>Cancelar</button><button class="confirm" ${this._busy ? "disabled" : ""}>${this._busy ? "Enviando…" : "Confirmar"}</button></div>
    </div></dialog>`;

    this.shadowRoot.querySelectorAll("button.mode").forEach((button) => {
      button.addEventListener("click", () => this._ask(button.dataset.entity, button.dataset.option, button.dataset.name, button.dataset.current));
    });
    this.shadowRoot.querySelectorAll("button[data-info]").forEach((button) => {
      button.addEventListener("click", () => VeggaUi.moreInfo(this, button.dataset.info));
    });
    this.shadowRoot.querySelector(".cancel")?.addEventListener("click", () => this._close());
    this.shadowRoot.querySelector(".confirm")?.addEventListener("click", () => this._apply());
    this.shadowRoot.querySelector("dialog")?.addEventListener("cancel", (event) => {
      if (this._busy) event.preventDefault();
      else this._close();
    });
  }
}

class VeggaProgramControlsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._pending = null;
    this._busy = false;
    this._message = "";
  }

  static getStubConfig() {
    return { controller: "vivero_agronic_17669", title: "Control de programas" };
  }

  setConfig(config) {
    if (!config?.controller) throw new Error("Debes indicar controller.");
    this._config = { title: "Control de programas", show_stop: true, confirm: true, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._scheduleActualHistory();
  }

  getCardSize() { return 8; }
  getGridOptions() { return { rows: 8, columns: 12, min_rows: 4, min_columns: 6 }; }

  _extractProgram(state) {
    const explicitName = state?.attributes?.program_name;
    const explicitAction = state?.attributes?.vegga_action;
    if (explicitName && (explicitAction === "start" || explicitAction === "stop")) {
      return {
        action: explicitAction,
        name: String(explicitName),
        number: Number(state?.attributes?.program_number) || null,
      };
    }
    const friendly = String(state?.attributes?.friendly_name || "");
    const lower = friendly.toLocaleLowerCase("es-ES");
    const starts = ["iniciar programa ", "arrancar programa "];
    const stops = ["parar programa ", "detener programa "];
    for (const marker of starts) {
      const index = lower.lastIndexOf(marker);
      if (index >= 0) return { action: "start", name: friendly.slice(index + marker.length).trim() };
    }
    for (const marker of stops) {
      const index = lower.lastIndexOf(marker);
      if (index >= 0) return { action: "stop", name: friendly.slice(index + marker.length).trim() };
    }

    const stem = state.entity_id.split(".")[1] || "";
    let match = stem.match(/(?:^|_)iniciar_programa_(.+)$/);
    if (match) return { action: "start", name: match[1].replaceAll("_", " ") };
    match = stem.match(/(?:^|_)parar_programa_(.+)$/);
    if (match) return { action: "stop", name: match[1].replaceAll("_", " ") };
    return null;
  }

  _programs() {
    const grouped = new Map();
    Object.values(this._hass?.states || {}).forEach((state) => {
      if (!state.entity_id.startsWith("button.")) return;
      const parsed = this._extractProgram(state);
      if (!parsed) return;
      if (state.attributes?.vegga_device_id !== undefined
          && !VeggaUi.belongs(state, this._config, this._hass)) return;
      if (!parsed.name) return;
      const key = parsed.name.toLocaleLowerCase("es-ES").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
      const current = grouped.get(key) || { name: parsed.name, start: null, stop: null };
      current[parsed.action] = state;
      grouped.set(key, current);
    });
    return Array.from(grouped.values()).sort((a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base", numeric: true }));
  }

  _activeNames() {
    const prefix = VeggaUi.prefix(this._config);
    const state = this._hass?.states?.[`sensor.${prefix}_programas_activos`];
    const values = Array.isArray(state?.attributes?.active_program_names) ? state.attributes.active_program_names : [];
    return new Set(values.map((value) => String(value).toLocaleLowerCase("es-ES").trim()));
  }

  _ask(entityId, action, name) {
    if (!entityId || this._busy) return;
    this._pending = { entityId, action, name };
    this._message = "";
    this._render();
    const dialog = this.shadowRoot.querySelector("dialog");
    if (this._config.confirm === false) this._apply();
    else if (dialog && !dialog.open) dialog.showModal();
  }

  _close() {
    if (this._busy) return;
    this.shadowRoot.querySelector("dialog")?.close();
    this._pending = null;
    this._message = "";
    this._render();
  }

  async _apply() {
    if (!this._hass || !this._pending || this._busy) return;
    this._busy = true;
    this._message = "Enviando orden al Agrónic…";
    this._render();
    this.shadowRoot.querySelector("dialog")?.showModal();
    const pending = this._pending;
    try {
      await this._hass.callService("button", "press", { entity_id: pending.entityId });
      this._busy = false;
      this._pending = null;
      this._message = "";
      this._render();
      VeggaUi.notify(this, `${pending.action === "start" ? "Iniciado" : "Detenido"}: ${pending.name}`);
    } catch (error) {
      this._busy = false;
      this._message = `No se pudo enviar la orden: ${error?.message || error}`;
      this._render();
      this.shadowRoot.querySelector("dialog")?.showModal();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const programs = this._programs();
    const activeNames = this._activeNames();
    const items = programs.map((program) => {
      const active = activeNames.has(program.name.toLocaleLowerCase("es-ES").trim());
      const infoEntity = program.start?.entity_id || program.stop?.entity_id;
      return `<div class="program ${active ? "active" : ""}">
        <div class="program-head">
          <button class="program-name" data-info="${VeggaUi.escape(infoEntity)}">${VeggaUi.escape(program.name)}<ha-icon icon="mdi:information-outline"></ha-icon></button>
          <span class="status">${active ? "En ejecución" : "Parado"}</span>
        </div>
        <div class="actions ${this._config.show_stop === false ? "single" : ""}">
          <button class="action start" data-entity="${VeggaUi.escape(program.start?.entity_id || "")}" data-action="start" data-name="${VeggaUi.escape(program.name)}" ${!program.start || this._busy ? "disabled" : ""}><ha-icon icon="mdi:play"></ha-icon>Iniciar</button>
          ${this._config.show_stop !== false ? `<button class="action stop" data-entity="${VeggaUi.escape(program.stop?.entity_id || "")}" data-action="stop" data-name="${VeggaUi.escape(program.name)}" ${!program.stop || this._busy ? "disabled" : ""}><ha-icon icon="mdi:stop"></ha-icon>Parar</button>` : ""}
        </div>
      </div>`;
    }).join("");

    const pending = this._pending;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{overflow:hidden}.wrap{padding:18px}.titlebar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.titlebar h2{margin:0;font-size:1.35rem}.count{color:var(--secondary-text-color);font-size:.82rem}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.program{padding:14px;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color)}.program.active{border-color:var(--success-color,#2e7d32);box-shadow:inset 4px 0 0 var(--success-color,#2e7d32)}.program-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:12px}.program-name{min-width:0;border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:700;text-align:left;padding:0;cursor:pointer;display:flex;align-items:center;gap:4px}.program-name:hover{color:var(--primary-color)}.program-name ha-icon{--mdc-icon-size:16px;color:var(--secondary-text-color)}.status{flex:0 0 auto;font-size:.74rem;padding:4px 8px;border-radius:999px;background:var(--secondary-background-color);color:var(--secondary-text-color)}.active .status{background:color-mix(in srgb,var(--success-color,#2e7d32) 16%,var(--card-background-color));color:var(--success-color,#2e7d32);font-weight:700}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.actions.single{grid-template-columns:1fr}.action{min-height:46px;border:1px solid var(--divider-color);border-radius:11px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px}.action:hover:not(:disabled){transform:translateY(-1px)}.action:disabled{opacity:.45;cursor:default}.action.start{border-color:color-mix(in srgb,var(--success-color,#2e7d32) 42%,var(--divider-color))}.action.start ha-icon{color:var(--success-color,#2e7d32)}.action.stop{border-color:color-mix(in srgb,var(--error-color,#d32f2f) 38%,var(--divider-color))}.action.stop ha-icon{color:var(--error-color,#d32f2f)}.empty{padding:22px;text-align:center;color:var(--secondary-text-color);border:1px solid var(--divider-color);border-radius:14px}dialog{width:min(460px,calc(100vw - 28px));border:0;border-radius:18px;padding:0;color:var(--primary-text-color);background:var(--card-background-color);box-shadow:0 14px 44px rgba(0,0,0,.4)}dialog::backdrop{background:rgba(0,0,0,.58)}.dialog-body{padding:24px}.dialog-title{font-size:1.18rem;font-weight:750;display:flex;align-items:center;gap:9px}.dialog-title ha-icon{color:var(--warning-color,#f9a825)}.change{margin:17px 0;padding:14px;border-radius:12px;background:var(--secondary-background-color)}.message{font-size:.9rem;color:var(--primary-color);margin-top:12px}.message.error{color:var(--error-color)}.dialog-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.dialog-actions button{min-height:42px;border-radius:10px;padding:0 16px;font:inherit;font-weight:700;cursor:pointer}.cancel{border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color)}.confirm{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff)}
      @media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:600px){.wrap{padding:12px}.grid{grid-template-columns:1fr}.titlebar h2{font-size:1.15rem}.action{min-height:50px}}
    </style><ha-card><div class="wrap">
      <div class="titlebar"><h2>${VeggaUi.escape(this._config.title)}</h2><span class="count">${programs.length} programas</span></div>
      ${items ? `<div class="grid">${items}</div>` : `<div class="empty">No se han encontrado los botones de control de programas.</div>`}
    </div></ha-card>
    <dialog><div class="dialog-body">
      <div class="dialog-title"><ha-icon icon="mdi:shield-alert"></ha-icon>Confirmar orden de programa</div>
      ${pending ? `<div class="change"><strong>${pending.action === "start" ? "Iniciar" : "Parar"}</strong> el programa <strong>${VeggaUi.escape(pending.name)}</strong>.</div><div>La orden se enviará inmediatamente al programador Agrónic.</div>` : ""}
      ${this._message ? `<div class="message ${this._message.startsWith("No se pudo") ? "error" : ""}">${VeggaUi.escape(this._message)}</div>` : ""}
      <div class="dialog-actions"><button class="cancel" ${this._busy ? "disabled" : ""}>Cancelar</button><button class="confirm" ${this._busy ? "disabled" : ""}>${this._busy ? "Enviando…" : "Confirmar"}</button></div>
    </div></dialog>`;

    this.shadowRoot.querySelectorAll("button.action").forEach((button) => {
      button.addEventListener("click", () => this._ask(button.dataset.entity, button.dataset.action, button.dataset.name));
    });
    this.shadowRoot.querySelectorAll("button[data-info]").forEach((button) => {
      button.addEventListener("click", () => VeggaUi.moreInfo(this, button.dataset.info));
    });
    this.shadowRoot.querySelector(".cancel")?.addEventListener("click", () => this._close());
    this.shadowRoot.querySelector(".confirm")?.addEventListener("click", () => this._apply());
    this.shadowRoot.querySelector("dialog")?.addEventListener("cancel", (event) => {
      if (this._busy) event.preventDefault();
      else this._close();
    });
  }
}

if (!customElements.get("vegga-overview-card")) customElements.define("vegga-overview-card", VeggaOverviewCard);
if (!customElements.get("vegga-sector-controls-card")) customElements.define("vegga-sector-controls-card", VeggaSectorControlsCard);
if (!customElements.get("vegga-program-controls-card")) customElements.define("vegga-program-controls-card", VeggaProgramControlsCard);

window.customCards = window.customCards || [];
[
  { type: "vegga-overview-card", name: "VEGGA - Resumen", description: "Riegos reales, consumos, inicio y fin por sector." },
  { type: "vegga-sector-controls-card", name: "VEGGA - Control de sectores", description: "Todos los sectores con Automático, Marcha y Paro." },
  { type: "vegga-program-controls-card", name: "VEGGA - Control de programas", description: "Inicio y parada de todos los programas Agrónic." },
].forEach((card) => {
  if (!window.customCards.some((existing) => existing.type === card.type)) window.customCards.push(card);
});

console.info(`%c VEGGA panel ${VEGGA_UI_VERSION} `, "color:white;background:#00897b;font-weight:bold;padding:3px 6px;border-radius:4px");
