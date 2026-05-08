"""Diagnostics support for the BanlanX FT001 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_LOCAL_NAME, CONF_MAC_ADDRESS, CONF_MODEL_CODE, DOMAIN
from .coordinator import BanlanxFT001Coordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for one FT001 config entry."""
    coordinator: BanlanxFT001Coordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get(CONF_PORT),
            "name": entry.data.get(CONF_NAME),
            "mac_address": entry.data.get(CONF_MAC_ADDRESS),
            "local_name": entry.data.get(CONF_LOCAL_NAME),
            "model_code": entry.data.get(CONF_MODEL_CODE),
        },
        "last_update_success": coordinator.last_update_success
        if coordinator is not None
        else None,
        "client_host": coordinator.client.host if coordinator is not None else None,
    }

    if coordinator is None or coordinator.data is None:
        return diagnostics

    status = coordinator.data
    diagnostics["status"] = {
        "firmware": status.firmware,
        "ssid": status.ssid,
        "ip_address": status.ip_address,
        "channels": {
            channel: {
                "power": state.power,
                "mode": state.mode,
                "effect": state.effect,
                "brightness": state.brightness,
                "rgb": state.rgb,
                "speed": state.speed,
                "length": state.length,
                "light_type": state.light_type,
            }
            for channel, state in status.channels.items()
        },
    }
    return diagnostics
