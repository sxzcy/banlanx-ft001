"""Config flow for the BanlanX FT001 integration."""

from __future__ import annotations

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
from .discovery import async_discover_ft001_host


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
                    discovery = await async_discover_ft001_host(host, timeout=3.0)
                    self._abort_if_host_configured(
                        host, port, discovery.mac_address if discovery else None
                    )
                    unique_id = (
                        discovery.mac_address
                        if discovery is not None and discovery.is_ft001
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
                    if discovery is not None:
                        data.update(
                            {
                                CONF_MAC_ADDRESS: discovery.mac_address,
                                CONF_LOCAL_NAME: discovery.local_name,
                                CONF_MODEL_CODE: discovery.model_code,
                            }
                        )
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
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
            errors=errors,
        )

    def _abort_if_host_configured(
        self, host: str, port: int, mac_address: str | None
    ) -> None:
        """Abort when this controller already exists under old or new metadata."""
        for entry in self._async_current_entries():
            if (
                entry.data.get(CONF_HOST) == host
                and entry.data.get(CONF_PORT, DEFAULT_PORT) == port
            ):
                raise AbortFlow("already_configured")
            if mac_address and entry.data.get(CONF_MAC_ADDRESS) == mac_address:
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
                    discovery = await async_discover_ft001_host(host, timeout=3.0)
                    new_data = dict(data)
                    new_data.update(
                        {
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_NAME: name,
                        }
                    )
                    if discovery is not None:
                        new_data.update(
                            {
                                CONF_MAC_ADDRESS: discovery.mac_address,
                                CONF_LOCAL_NAME: discovery.local_name,
                                CONF_MODEL_CODE: discovery.model_code,
                            }
                        )
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
                    ): str,
                    vol.Required(
                        CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)
                    ): int,
                    vol.Optional(
                        CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)
                    ): str,
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
