from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import VeggaApi
from .const import CONF_DEVICE_ID, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import VeggaCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
]

VERSION = "0.5.4"
FRONTEND_BASE = "/vegga_static"
FRONTEND_FILES = (
    "vegga-sector-card.js",
    "vegga-cards-v0.4.31.js",
    "vegga-overview-card.js",
)
OVERVIEW_MODULE_URL = f"{FRONTEND_BASE}/vegga-overview-card.js?v={VERSION}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register VEGGA frontend files before config entries are loaded."""
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"{FRONTEND_BASE}/{filename}",
                str(frontend_dir / filename),
                False,
            )
            for filename in FRONTEND_FILES
        ]
    )

    # Home Assistant exposes this helper specifically so custom integrations
    # can load frontend modules without requiring a manual Lovelace resource.
    add_extra_js_url(hass, OVERVIEW_MODULE_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a VEGGA config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

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

    domain_data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a VEGGA config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
