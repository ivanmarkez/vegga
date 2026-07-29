from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er

from .api import VeggaApi
from .const import CONF_DEVICE_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import VeggaCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SELECT]

FRONTEND_PATH = "/vegga_static/vegga-sector-card.js"
FRONTEND_URL = f"{FRONTEND_PATH}?v=0.4.46"
LEGACY_FRONTEND_PATH = "/vegga_static/vegga-sector-card-0.4.44.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("_frontend_registered"):
        frontend_file = Path(__file__).parent / "frontend" / "vegga-sector-card.js"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(FRONTEND_PATH, str(frontend_file), True),
                StaticPathConfig(LEGACY_FRONTEND_PATH, str(frontend_file), True),
            ]
        )
        add_extra_js_url(hass, FRONTEND_URL)
        domain_data["_frontend_registered"] = True

    api = VeggaApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_DEVICE_ID],
    )
    scan_interval = int(
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
    )

    coordinator = VeggaCoordinator(hass, entry, api, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    # Clean registry entries left by releases that created entities without a
    # usable data source. Search within this config entry instead of relying on
    # a platform lookup, because older HA versions may retain a different
    # platform association for restored entities.
    registry = er.async_get(hass)
    obsolete_unique_ids = {
        f"{api.device_id}_pressure",
        f"{api.device_id}_history_anomaly_count",
    }
    for registry_entry in list(registry.entities.values()):
        if registry_entry.unique_id not in obsolete_unique_ids:
            continue
        if (
            registry_entry.config_entry_id != entry.entry_id
            and registry_entry.platform != DOMAIN
        ):
            continue
        hass.states.async_remove(registry_entry.entity_id)
        registry.async_remove(registry_entry.entity_id)

    domain_data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
