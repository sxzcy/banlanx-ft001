"""BanlanX FT001 Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .client import BanlanxFT001Client
from .const import (
    CONF_LOCAL_NAME,
    CONF_MAC_ADDRESS,
    CONF_MODEL_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import BanlanxFT001Coordinator
from .discovery import async_discover_ft001_host


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BanlanX FT001 from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    await _async_enrich_entry_discovery(hass, entry, host)

    client = BanlanxFT001Client(host, port)
    coordinator = BanlanxFT001Coordinator(
        hass,
        entry,
        client,
        name,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_update_device_registry(hass, entry)
    return True


async def _async_enrich_entry_discovery(
    hass: HomeAssistant, entry: ConfigEntry, host: str
) -> None:
    """Add UDP discovery metadata to older entries without changing entity IDs."""
    if entry.data.get(CONF_MAC_ADDRESS):
        return

    discovery = await async_discover_ft001_host(host, timeout=2.0)
    if discovery is None or not discovery.is_ft001:
        return

    data = dict(entry.data)
    data.update(
        {
            CONF_MAC_ADDRESS: discovery.mac_address,
            CONF_LOCAL_NAME: discovery.local_name,
            CONF_MODEL_CODE: discovery.model_code,
        }
    )
    hass.config_entries.async_update_entry(entry, data=data)


def _async_update_device_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Merge the discovered WiFi MAC into an existing device registry entry."""
    mac_address = entry.data.get(CONF_MAC_ADDRESS)
    if not mac_address or not entry.unique_id:
        return

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.unique_id)})
    if device is None:
        return

    device_registry.async_update_device(
        device.id,
        merge_connections={(dr.CONNECTION_NETWORK_MAC, mac_address)},
    )


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry after options or connection settings change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
