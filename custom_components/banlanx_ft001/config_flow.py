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
from .discovery import (
    FT001Discovery,
    async_discover_ft001,
    async_discover_ft001_host,
    async_get_broadcast_addresses,
)

MIN_PORT = 1
MAX_PORT = 65535
CONF_DEVICE = "device"
MANUAL_DEVICE_CHOICE = "__manual__"

OPTIONS_FLOW_BASE = getattr(
    config_entries, "OptionsFlowWithReload", config_entries.OptionsFlow
)


def _strip_string(value: str) -> str:
    """Return a stripped string value."""
    return value.strip()


HOST_SCHEMA = vol.All(str, _strip_string, vol.Length(min=1))
PORT_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=MIN_PORT, max=MAX_PORT))
NAME_SCHEMA = vol.All(str, _strip_string)


class BanlanxFT001ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BanlanX FT001."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        super().__init__()
        self._discovered_devices: dict[str, FT001Discovery] = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return BanlanxFT001OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial setup with automatic LAN discovery fallback to manual."""
        if user_input is not None:
            return await self._async_validate_and_create(user_input, step_id="user")

        addresses = await async_get_broadcast_addresses(self.hass)
        discovered = await async_discover_ft001(timeout=2.0, addresses=addresses)
        unconfigured: dict[str, FT001Discovery] = {}
        current_entries = list(self._async_current_entries())
        for device in discovered:
            if not device.is_ft001:
                continue
            if _is_controller_configured(
                current_entries,
                device.host,
                DEFAULT_PORT,
                device.mac_address,
            ):
                continue
            unconfigured[device.host] = device

        if unconfigured:
            self._discovered_devices = unconfigured
            return await self.async_step_discover()

        return self._show_manual_form(step_id="user")

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick a discovered FT001 controller or enter IP manually."""
        errors: dict[str, str] = {}
        if user_input is not None:
            choice = user_input[CONF_DEVICE]
            if choice == MANUAL_DEVICE_CHOICE:
                return await self.async_step_manual()
            selected = self._discovered_devices.get(choice)
            if selected is not None:
                name = user_input.get(CONF_NAME) or DEFAULT_NAME
                return await self._async_validate_and_create(
                    {
                        CONF_HOST: selected.host,
                        CONF_PORT: DEFAULT_PORT,
                        CONF_NAME: name,
                    },
                    step_id="discover",
                    preverified_discovery=selected,
                )
            errors["base"] = "cannot_connect"

        choices = {
            host: (
                f"{dev.local_name or 'FT001'} ({host} / {dev.mac_address})"
            )
            for host, dev in sorted(self._discovered_devices.items())
        }
        choices[MANUAL_DEVICE_CHOICE] = "Manual IP / Host"

        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): vol.In(choices),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): NAME_SCHEMA,
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual host and port entry."""
        if user_input is not None:
            return await self._async_validate_and_create(user_input, step_id="manual")
        return self._show_manual_form(step_id="manual")

    async def _async_validate_and_create(
        self,
        user_input: dict[str, Any],
        *,
        step_id: str,
        preverified_discovery: FT001Discovery | None = None,
    ) -> FlowResult:
        """Validate TCP/UDP connectivity and create the config entry."""
        errors: dict[str, str] = {}
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
                discovery = (
                    preverified_discovery
                    if preverified_discovery is not None
                    and preverified_discovery.is_ft001
                    else await _async_get_verified_discovery(host)
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
                self._abort_if_host_configured(
                    host, port, discovery.mac_address if discovery else None
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

        if step_id == "discover":
            return self._show_manual_form(
                step_id="manual",
                errors=errors,
                default_host=host,
                default_port=port,
                default_name=name,
            )
        return self._show_manual_form(
            step_id=step_id,
            errors=errors,
            default_host=host,
            default_port=port,
            default_name=name,
        )

    def _show_manual_form(
        self,
        *,
        step_id: str,
        errors: dict[str, str] | None = None,
        default_host: str = "",
        default_port: int = DEFAULT_PORT,
        default_name: str = DEFAULT_NAME,
    ) -> FlowResult:
        """Render the manual connection form."""
        schema_fields: dict[Any, Any] = {
            vol.Required(CONF_HOST, default=default_host): HOST_SCHEMA
            if default_host
            else HOST_SCHEMA,
            vol.Required(CONF_PORT, default=default_port): PORT_SCHEMA,
            vol.Optional(CONF_NAME, default=default_name): NAME_SCHEMA,
        }
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema_fields),
            errors=errors or {},
        )

    def _abort_if_host_configured(
        self, host: str, port: int, mac_address: str | None
    ) -> None:
        """Abort when this controller already exists under old or new metadata."""
        if _is_controller_configured(
            self._async_current_entries(), host, port, mac_address
        ):
            raise AbortFlow("already_configured")


class BanlanxFT001OptionsFlow(OPTIONS_FLOW_BASE):
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
                        data_changed = self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            title=name,
                            data=new_data,
                        )
                        new_options = {
                            CONF_SCAN_INTERVAL: scan_interval,
                        }
                        options_changed = dict(options) != new_options
                        # OptionsFlowWithReload reloads only when options change;
                        # schedule reload explicitly when only entry data changed.
                        if data_changed and not options_changed:
                            if hasattr(
                                self.hass.config_entries, "async_schedule_reload"
                            ):
                                self.hass.config_entries.async_schedule_reload(
                                    self.config_entry.entry_id
                                )
                            else:
                                await self.hass.config_entries.async_reload(
                                    self.config_entry.entry_id
                                )
                        return self.async_create_entry(
                            title="",
                            data=new_options,
                        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(
                            user_input[CONF_HOST]
                            if user_input is not None
                            else data.get(CONF_HOST, "")
                        ),
                    ): HOST_SCHEMA,
                    vol.Required(
                        CONF_PORT,
                        default=(
                            user_input[CONF_PORT]
                            if user_input is not None
                            else data.get(CONF_PORT, DEFAULT_PORT)
                        ),
                    ): PORT_SCHEMA,
                    vol.Optional(
                        CONF_NAME,
                        default=(
                            user_input.get(CONF_NAME, DEFAULT_NAME)
                            if user_input is not None
                            else data.get(CONF_NAME, DEFAULT_NAME)
                        ),
                    ): NAME_SCHEMA,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=(
                            user_input[CONF_SCAN_INTERVAL]
                            if user_input is not None
                            else options.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            )
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
