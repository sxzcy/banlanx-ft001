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
    entry.runtime_data = coordinator
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
    """Sync MAC connection, display name, and firmware to the device registry."""
    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    mac_address = entry.data.get(CONF_MAC_ADDRESS)
    device_id = entry.unique_id or mac_address or (f"{host}:{port}" if host else None)
    if not device_id:
        return

    device_registry = dr.async_get(hass)
    identifier = (DOMAIN, device_id)
    if hasattr(device_registry, "async_get_device_by_identifier"):
        device = device_registry.async_get_device_by_identifier(
            identifier,
            entry.entry_id,
        )
    else:
        device = device_registry.async_get_device(identifiers={identifier})
    if device is None:
        return

    update_kwargs: dict[str, object] = {}
    if mac_address:
        update_kwargs["new_connections"] = set(device.connections) | {
            (dr.CONNECTION_NETWORK_MAC, mac_address)
        }

    configured_name = entry.data.get(CONF_NAME)
    if configured_name and getattr(device, "name", None) != configured_name:
        update_kwargs["name"] = configured_name

    coordinator: BanlanxFT001Coordinator | None = getattr(entry, "runtime_data", None)
    firmware = (
        coordinator.data.firmware
        if coordinator is not None and coordinator.data is not None
        else None
    )
    if firmware and getattr(device, "sw_version", None) != firmware:
        update_kwargs["sw_version"] = firmware

    if update_kwargs:
        device_registry.async_update_device(device.id, **update_kwargs)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
