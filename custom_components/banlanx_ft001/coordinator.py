"""Coordinator for the BanlanX FT001 integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    BanlanxFT001Client,
    BanlanxFT001ConnectionError,
    BanlanxFT001Error,
    FT001Status,
)
from .const import (
    CONF_LOCAL_NAME,
    CONF_MAC_ADDRESS,
    CONF_MODEL_CODE,
    DEFAULT_SCAN_INTERVAL,
)
from .discovery import FT001Discovery, async_discover_ft001

_LOGGER = logging.getLogger(__name__)
DISCOVERY_COOLDOWN_SECONDS = 300.0


class BanlanxFT001Coordinator(DataUpdateCoordinator[FT001Status]):
    """Poll a BanlanX FT001 controller."""

    def __init__(
        self,
        hass,
        entry: ConfigEntry,
        client: BanlanxFT001Client,
        name: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.client = client
        self._last_discovery_attempt: float | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> FT001Status:
        """Fetch status from the controller."""
        try:
            status = await self.client.async_get_status()
        except BanlanxFT001ConnectionError as ex:
            if await self._async_recover_host():
                try:
                    status = await self.client.async_get_status()
                except BanlanxFT001Error as retry_ex:
                    raise UpdateFailed(str(retry_ex)) from retry_ex
                self._last_discovery_attempt = None
                return status
            raise UpdateFailed(str(ex)) from ex
        except BanlanxFT001Error as ex:
            raise UpdateFailed(str(ex)) from ex
        self._last_discovery_attempt = None
        return status

    async def _async_recover_host(self) -> bool:
        """Find the controller by MAC when its configured IP stops responding."""
        mac_address = self.entry.data.get(CONF_MAC_ADDRESS)
        if not mac_address:
            return False

        now = time.monotonic()
        if (
            self._last_discovery_attempt is not None
            and now - self._last_discovery_attempt < DISCOVERY_COOLDOWN_SECONDS
        ):
            return False
        self._last_discovery_attempt = now

        discovery = await self._async_find_discovery_by_mac(mac_address)
        if discovery is None or discovery.host == self.client.host:
            return False

        _LOGGER.info(
            "Updating FT001 host for %s from %s to %s",
            mac_address,
            self.client.host,
            discovery.host,
        )
        self.client.host = discovery.host
        data = dict(self.entry.data)
        data.update(
            {
                CONF_HOST: discovery.host,
                CONF_MAC_ADDRESS: discovery.mac_address,
                CONF_LOCAL_NAME: discovery.local_name,
                CONF_MODEL_CODE: discovery.model_code,
            }
        )
        self.hass.config_entries.async_update_entry(self.entry, data=data)
        self.entry = (
            self.hass.config_entries.async_get_entry(self.entry.entry_id) or self.entry
        )
        return True

    async def _async_find_discovery_by_mac(
        self, mac_address: str
    ) -> FT001Discovery | None:
        """Return a discovered FT001 controller by MAC address."""
        target = mac_address.upper()
        for discovery in await async_discover_ft001(timeout=3.0):
            if discovery.is_ft001 and discovery.mac_address.upper() == target:
                return discovery
        return None
