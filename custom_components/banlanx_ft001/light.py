"""Light platform for the BanlanX FT001 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import (
    EFFECT_SOLID,
    FT001_EFFECT_LIST,
    BanlanxFT001Error,
    FT001ChannelState,
)
from .const import (
    CONF_MAC_ADDRESS,
    CONF_MODEL_CODE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    LIGHT_ICON,
)
from .coordinator import BanlanxFT001Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FT001 light entities."""
    coordinator: BanlanxFT001Coordinator = entry.runtime_data
    async_add_entities(
        [
            BanlanxFT001Light(coordinator, entry, 1),
            BanlanxFT001Light(coordinator, entry, 2),
        ]
    )


def build_device_info(
    coordinator: BanlanxFT001Coordinator,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Build shared DeviceInfo dictionary for FT001 entities."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    device_id = (
        entry.unique_id or entry.data.get(CONF_MAC_ADDRESS) or f"{host}:{port}"
    )
    device_info: dict[str, Any] = {
        "identifiers": {(DOMAIN, device_id)},
        "manufacturer": "SPLED (BanlanX)",
        "model": "FT001",
        "name": name,
    }
    if mac_address := entry.data.get(CONF_MAC_ADDRESS):
        device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, mac_address)}
    if coordinator.data is not None and coordinator.data.firmware:
        device_info["sw_version"] = coordinator.data.firmware
    return device_info


class BanlanxFT001Light(CoordinatorEntity[BanlanxFT001Coordinator], LightEntity):
    """One FT001 RGB output channel."""

    _attr_has_entity_name = True
    _attr_icon = LIGHT_ICON
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = FT001_EFFECT_LIST

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
        device_id = (
            entry.unique_id or entry.data.get(CONF_MAC_ADDRESS) or f"{host}:{port}"
        )
        self._attr_translation_key = f"channel_{channel}"
        self._attr_unique_id = f"{device_id}:channel_{channel}"
        self._attr_device_info = build_device_info(coordinator, entry)

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
    def effect(self) -> str | None:
        """Return current effect name."""
        state = self._state
        return None if state is None else state.effect_name

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose low-level state useful while validating this controller."""
        state = self._state
        if state is None:
            return None
        attrs = {
            "ft001_channel": state.channel,
            "light_type": state.light_type,
            "mode": state.mode,
            "effect_code": state.effect,
            "speed": state.speed,
            "length": state.length,
        }
        if firmware := self.coordinator.data.firmware:
            attrs["firmware"] = firmware
        entry_data = self.coordinator.entry.data
        if model_code := entry_data.get(CONF_MODEL_CODE):
            attrs["model_code"] = model_code
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on or update this channel."""
        state = self._state
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        effect = kwargs.get(ATTR_EFFECT)
        power_on = state is None or not state.power

        try:
            if effect is not None:
                if effect == EFFECT_SOLID and rgb is not None:
                    level = (
                        brightness
                        if brightness is not None
                        else (state.brightness if state is not None else 255)
                    )
                    await self.coordinator.async_execute_command(
                        lambda: self.coordinator.client.async_set_static_color(
                            self._channel,
                            rgb,
                            level,
                            power_on=power_on,
                            fetch_status=True,
                        )
                    )
                else:
                    await self.coordinator.async_execute_command(
                        lambda: self.coordinator.client.async_set_effect(
                            self._channel,
                            effect,
                            power_on=power_on,
                            brightness=brightness,
                            fetch_status=True,
                        )
                    )
            elif rgb is not None:
                level = (
                    brightness
                    if brightness is not None
                    else (state.brightness if state is not None else 255)
                )
                await self.coordinator.async_execute_command(
                    lambda: self.coordinator.client.async_set_static_color(
                        self._channel,
                        rgb,
                        level,
                        power_on=power_on,
                        fetch_status=True,
                    )
                )
            elif brightness is not None:
                await self.coordinator.async_execute_command(
                    lambda: self.coordinator.client.async_set_brightness(
                        self._channel,
                        brightness,
                        power_on=power_on,
                        fetch_status=True,
                    )
                )
            else:
                await self.coordinator.async_execute_command(
                    lambda: self.coordinator.client.async_set_power(
                        self._channel,
                        True,
                        fetch_status=True,
                    )
                )
        except (BanlanxFT001Error, ValueError) as ex:
            raise HomeAssistantError(
                f"Failed to update FT001 channel {self._channel}: {ex}"
            ) from ex

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off this channel."""
        try:
            await self.coordinator.async_execute_command(
                lambda: self.coordinator.client.async_set_power(
                    self._channel,
                    False,
                    fetch_status=True,
                )
            )
        except (BanlanxFT001Error, ValueError) as ex:
            raise HomeAssistantError(
                f"Failed to turn off FT001 channel {self._channel}: {ex}"
            ) from ex
