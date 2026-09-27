"""Serve and automatically maintain VEGGA dashboard resources."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
VERSION = "0.5.30"
BASE = "/vegga_static"
CARDS = ("vegga-program-days-card.js", "vegga-overview-card.js")
LEGACY = (
    "vegga-sector-card.js",
    "vegga-cards-v0.4.31.js",
    "vegga-cards-v0.4.32.js",
    "vegga-loader.js",
)


def _local_path(url: str) -> str:
    """Only manage our relative resource URLs; leave other resources alone."""
    parts = urlsplit(url)
    return parts.path if not parts.scheme and not parts.netloc else ""


async def async_sync_resources(resources, urls: list[str]) -> None:
    """Load storage BEFORE editing, then migrate only our owned entries."""
    if not hasattr(resources, "async_create_item"):
        # YAML resource collections are read-only. Extra modules still load.
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    for url in urls:
        path = _local_path(url)
        aliases = {path}
        if path == f"{BASE}/vegga-program-days-card.js":
            aliases.add(f"{BASE}/vegga-loader.js")
        matches = [
            item for item in list(resources.async_items())
            if _local_path(item.get("url", "")) in aliases
        ]
        if not matches:
            await resources.async_create_item({"url": url, "res_type": "module"})
            continue
        # Prefer the direct card's existing ID to a legacy loader ID.
        matches.sort(key=lambda item: _local_path(item["url"]) != path)
        keep, *duplicates = matches
        if keep.get("url") != url or keep.get("type") != "module":
            await resources.async_update_item(
                keep["id"], {"url": url, "res_type": "module"}
            )
        for duplicate in duplicates:
            await resources.async_delete_item(duplicate["id"])


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register independent modules through frontend and Lovelace."""
    directory = Path(__file__).parent / "frontend"
    existing = await hass.async_add_executor_job(
        lambda: [name for name in (*CARDS, *LEGACY) if (directory / name).is_file()]
    )
    await hass.http.async_register_static_paths([
        StaticPathConfig(f"{BASE}/{name}", str(directory / name), False)
        for name in existing
    ])
    urls = [f"{BASE}/{name}?v={VERSION}" for name in CARDS if name in existing]
    for url in urls:
        # No shared import dependency: one failing card cannot block the other.
        add_extra_js_url(hass, url)
    missing = set(CARDS) - set(existing)
    if missing:
        _LOGGER.error("VEGGA frontend files missing: %s", sorted(missing))

    try:
        lovelace = hass.data[LOVELACE_DATA]
        resources = (
            lovelace.get("resources") if isinstance(lovelace, dict)
            else lovelace.resources
        )
        if resources is not None:
            await async_sync_resources(resources, urls)
    except Exception:
        # A dashboard problem must not prevent irrigation sensor startup.
        _LOGGER.exception(
            "Could not update VEGGA Lovelace resources; extra modules remain active"
        )
