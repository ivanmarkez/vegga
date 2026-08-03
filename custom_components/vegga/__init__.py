from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VeggaApi
from .const import CONF_DEVICE_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import VeggaCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SELECT]
VERSION = "0.5.1"
FRONTEND_PATH = "/vegga_static/vegga-overview-card.js"
FRONTEND_URL = f"{FRONTEND_PATH}?v={VERSION}"


def _register_frontend_resource(hass: HomeAssistant) -> None:
    """Register the Lovelace card without requiring a manual resource."""
    try:
        from homeassistant.components.frontend import add_extra_js_url
        add_extra_js_url(hass, FRONTEND_URL)
        return
    except (ImportError, AttributeError, TypeError):
        pass

    try:
        from homeassistant.components.frontend import async_add_extra_js_url
        result = async_add_extra_js_url(hass, FRONTEND_URL)
        if result is not None:
            hass.async_create_task(result)
    except (ImportError, AttributeError, TypeError):
        pass


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("_frontend_registered"):
        frontend_file = Path(__file__).parent / "frontend" / "vegga-overview-card.js"
        await hass.http.async_register_static_paths([
            StaticPathConfig(FRONTEND_PATH, str(frontend_file), False),
        ])
        _register_frontend_resource(hass)
        domain_data["_frontend_registered"] = True

    api = VeggaApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_DEVICE_ID],
    )
    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
    coordinator = VeggaCoordinator(hass, entry, api, scan_interval)
    await coordinator.async_config_entry_first_refresh()
    domain_data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
