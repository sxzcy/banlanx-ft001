"""Number platform for BanlanX FT001 dynamic effect speed."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BanlanxFT001Error, FT001ChannelState
from .const import (
    CONF_MAC_ADDRESS,
    DEFAULT_PORT,
    MAX_EFFECT_SPEED,
    MIN_EFFECT_SPEED,
)
from .coordinator import BanlanxFT001Coordinator
from .light import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FT001 effect speed number entities."""
    coordinator: BanlanxFT001Coordinator = entry.runtime_data
    async_add_entities(
        [
            BanlanxFT001SpeedNumber(coordinator, entry, 1),
            BanlanxFT001SpeedNumber(coordinator, entry, 2),
        ]
    )


class BanlanxFT001SpeedNumber(
    CoordinatorEntity[BanlanxFT001Coordinator], NumberEntity
):
    """Dynamic effect speed slider for one FT001 channel."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:speedometer"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = float(MIN_EFFECT_SPEED)
    _attr_native_max_value = float(MAX_EFFECT_SPEED)
    _attr_native_step = 1.0

    def __init__(
        self,
        coordinator: BanlanxFT001Coordinator,
        entry: ConfigEntry,
        channel: int,
    ) -> None:
        """Initialize the effect speed entity."""
        super().__init__(coordinator)
        self._channel = channel
        host = entry.data[CONF_HOST]
        port = entry.data.get(CONF_PORT, DEFAULT_PORT)
        device_id = (
            entry.unique_id or entry.data.get(CONF_MAC_ADDRESS) or f"{host}:{port}"
        )
        self._attr_translation_key = f"channel_{channel}_speed"
        self._attr_unique_id = f"{device_id}:channel_{channel}_speed"
        self._attr_device_info = build_device_info(coordinator, entry)

    @property
    def _state(self) -> FT001ChannelState | None:
        """Return current channel state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.channels.get(self._channel)

    @property
    def available(self) -> bool:
        """Return if this entity is available."""
        return super().available and self._state is not None

    @property
    def native_value(self) -> float | None:
        """Return current dynamic effect speed."""
        state = self._state
        return None if state is None else float(state.speed)

    async def async_set_native_value(self, value: float) -> None:
        """Update dynamic effect speed for this channel."""
        speed = int(round(value))
        try:
            await self.coordinator.async_execute_command(
                lambda: self.coordinator.client.async_set_speed(
                    self._channel,
                    speed,
                    fetch_status=True,
                )
            )
        except (BanlanxFT001Error, ValueError) as ex:
            raise HomeAssistantError(
                f"Failed to set speed for FT001 channel {self._channel}: {ex}"
            ) from ex
