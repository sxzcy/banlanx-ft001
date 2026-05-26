"""Config flow for the BanlanX FT001 integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import AbortFlow, FlowResult

from .client import BanlanxFT001Client, BanlanxFT001Error
from .const import (
    CONF_LOCAL_NAME,
    CONF_MAC_ADDRESS,
    CONF_MODEL_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .discovery import FT001Discovery, async_discover_ft001_host

MIN_PORT = 1
MAX_PORT = 65535


def _strip_string(value: str) -> str:
    """Return a stripped string value."""
    return value.strip()


HOST_SCHEMA = vol.All(str, _strip_string, vol.Length(min=1))
PORT_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=MIN_PORT, max=MAX_PORT))
NAME_SCHEMA = vol.All(str, _strip_string)


class BanlanxFT001ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BanlanX FT001."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return BanlanxFT001OptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            name = user_input.get(CONF_NAME) or DEFAULT_NAME

            client = BanlanxFT001Client(host, port)
            try:
                status = await client.async_get_status()
            except BanlanxFT001Error:
                errors["base"] = "cannot_connect"
            else:
                if not _looks_like_ft001(status.channels):
                    errors["base"] = "invalid_model"
                else:
                    discovery = await _async_get_verified_discovery(host)
                    self._abort_if_host_configured(
                        host, port, discovery.mac_address if discovery else None
                    )
                    unique_id = (
                        discovery.mac_address
                        if discovery is not None
                        else f"{host}:{port}"
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: host, CONF_PORT: port}
                    )
                    data = {
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_NAME: name,
                    }
                    data.update(_discovery_data(discovery))
                    return self.async_create_entry(
                        title=name,
                        data=data,
                        options={
                            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): HOST_SCHEMA,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_SCHEMA,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): NAME_SCHEMA,
                }
            ),
            errors=errors,
        )

    def _abort_if_host_configured(
        self, host: str, port: int, mac_address: str | None
    ) -> None:
        """Abort when this controller already exists under old or new metadata."""
        if _is_controller_configured(
            self._async_current_entries(), host, port, mac_address
        ):
            raise AbortFlow("already_configured")


class BanlanxFT001OptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle options for BanlanX FT001."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage editable connection and polling settings."""
        errors: dict[str, str] = {}
        data = self.config_entry.data
        options = self.config_entry.options

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            name = user_input.get(CONF_NAME) or DEFAULT_NAME
            scan_interval = user_input[CONF_SCAN_INTERVAL]

            client = BanlanxFT001Client(host, port)
            try:
                status = await client.async_get_status()
            except BanlanxFT001Error:
                errors["base"] = "cannot_connect"
            else:
                if not _looks_like_ft001(status.channels):
                    errors["base"] = "invalid_model"
                else:
                    discovery = await _async_get_verified_discovery(host)
                    current_mac = data.get(CONF_MAC_ADDRESS)
                    if (
                        current_mac
                        and discovery is not None
                        and discovery.mac_address.upper() != current_mac.upper()
                    ):
                        errors["base"] = "different_device"
                    elif _is_controller_configured(
                        self.hass.config_entries.async_entries(DOMAIN),
                        host,
                        port,
                        discovery.mac_address if discovery else current_mac,
                        ignore_entry_id=self.config_entry.entry_id,
                    ):
                        errors["base"] = "already_configured"
                    else:
                        new_data = dict(data)
                        new_data.update(
                            {
                                CONF_HOST: host,
                                CONF_PORT: port,
                                CONF_NAME: name,
                            }
                        )
                        new_data.update(_discovery_data(discovery))
                        self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            title=name,
                            data=new_data,
                        )
                        return self.async_create_entry(
                            title="",
                            data={
                                CONF_SCAN_INTERVAL: scan_interval,
                            },
                        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=data.get(CONF_HOST, "")
                    ): HOST_SCHEMA,
                    vol.Required(
                        CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)
                    ): PORT_SCHEMA,
                    vol.Optional(
                        CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)
                    ): NAME_SCHEMA,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )


def _looks_like_ft001(channels: dict) -> bool:
    """Return true for the verified FT001 two-channel RGB PWM layout."""
    return (
        1 in channels
        and 2 in channels
        and channels[1].light_type == 5
        and channels[2].light_type == 5
    )


async def _async_get_verified_discovery(host: str) -> FT001Discovery | None:
    """Return discovery metadata only when it matches FT001."""
    discovery = await async_discover_ft001_host(host, timeout=3.0)
    if discovery is None or not discovery.is_ft001:
        return None
    return discovery


def _discovery_data(discovery: FT001Discovery | None) -> dict[str, str | int | None]:
    """Return config entry fields for a verified discovery result."""
    if discovery is None:
        return {}
    return {
        CONF_MAC_ADDRESS: discovery.mac_address,
        CONF_LOCAL_NAME: discovery.local_name,
        CONF_MODEL_CODE: discovery.model_code,
    }


def _is_controller_configured(
    entries: Iterable[config_entries.ConfigEntry],
    host: str,
    port: int,
    mac_address: str | None,
    *,
    ignore_entry_id: str | None = None,
) -> bool:
    """Return true when another config entry already points at this controller."""
    for entry in entries:
        if ignore_entry_id is not None and entry.entry_id == ignore_entry_id:
            continue
        if (
            entry.data.get(CONF_HOST) == host
            and entry.data.get(CONF_PORT, DEFAULT_PORT) == port
        ):
            return True
        if (
            mac_address
            and entry.data.get(CONF_MAC_ADDRESS, "").upper() == mac_address.upper()
        ):
            return True
    return False
