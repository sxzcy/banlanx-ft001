"""Light platform for the BanlanX FT001 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import FT001ChannelState
from .const import (
    CONF_LOCAL_NAME,
    CONF_MAC_ADDRESS,
    CONF_MODEL_CODE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import BanlanxFT001Coordinator

CHANNEL_NAMES = {
    1: "通道 1",
    2: "通道 2",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FT001 light entities."""
    coordinator: BanlanxFT001Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BanlanxFT001Light(coordinator, entry, 1),
            BanlanxFT001Light(coordinator, entry, 2),
        ]
    )


class BanlanxFT001Light(CoordinatorEntity[BanlanxFT001Coordinator], LightEntity):
    """One FT001 RGB output channel."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(
        self,
        coordinator: BanlanxFT001Coordinator,
        entry: ConfigEntry,
        channel: int,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator)
        self._channel = channel
        host = entry.data[CONF_HOST]
        port = entry.data.get(CONF_PORT, DEFAULT_PORT)
        name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        device_id = entry.unique_id or entry.data.get(CONF_MAC_ADDRESS) or f"{host}:{port}"
        self._attr_name = f"{name} {CHANNEL_NAMES[channel]}"
        self._attr_unique_id = f"{device_id}:channel_{channel}"
        device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "manufacturer": "SPLED (BanlanX)",
            "model": "FT001",
            "name": name,
        }
        if mac_address := entry.data.get(CONF_MAC_ADDRESS):
            device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, mac_address)}
        self._attr_device_info = device_info

    @property
    def _state(self) -> FT001ChannelState | None:
        """Return current channel state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.channels.get(self._channel)

    @property
    def available(self) -> bool:
        """Return if this channel is available."""
        return super().available and self._state is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the channel is on."""
        state = self._state
        return None if state is None else state.power

    @property
    def brightness(self) -> int | None:
        """Return channel brightness."""
        state = self._state
        return None if state is None else state.brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return current RGB color."""
        state = self._state
        return None if state is None else state.rgb

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose low-level state useful while validating this new controller."""
        state = self._state
        if state is None:
            return None
        attrs = {
            "ft001_channel": state.channel,
            "light_type": state.light_type,
            "mode": state.mode,
            "effect": state.effect,
            "speed": state.speed,
            "length": state.length,
            "firmware": self.coordinator.data.firmware,
            "controller_ip": self.coordinator.data.ip_address,
            "controller_ssid": self.coordinator.data.ssid,
        }
        entry_data = self.coordinator.entry.data
        if mac_address := entry_data.get(CONF_MAC_ADDRESS):
            attrs["mac_address"] = mac_address
        if local_name := entry_data.get(CONF_LOCAL_NAME):
            attrs["local_name"] = local_name
        if model_code := entry_data.get(CONF_MODEL_CODE):
            attrs["model_code"] = model_code
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on or update this channel."""
        state = self._state
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        if rgb is None and brightness is None:
            await self.coordinator.client.async_set_power(self._channel, True)
        else:
            if state is not None and not state.power:
                await self.coordinator.client.async_set_power(self._channel, True)
            await self.coordinator.client.async_set_static_color(
                self._channel,
                rgb or (state.rgb if state is not None else (255, 255, 255)),
                brightness
                if brightness is not None
                else (state.brightness if state is not None else 255),
            )

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off this channel."""
        await self.coordinator.client.async_set_power(self._channel, False)
        await self.coordinator.async_request_refresh()
