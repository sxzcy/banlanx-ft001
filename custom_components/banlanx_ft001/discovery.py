"""UDP discovery helpers for BanlanX FT001 WiFi controllers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
import selectors
import socket
import time
from typing import Any

from .const import FT001_MODEL_CODE

SPNET_DISCOVERY_PORT = 6454
SPNET_DISCOVERY_MESSAGE = bytes.fromhex("53704e65740000200000000002e0")
SPNET_DISCOVERY_RESPONSE = bytes.fromhex("53704e6574000021000000000001")

BROADCAST_ADDRESS = "<broadcast>"
BROADCAST_FREQUENCY = 8
MAX_RESPONSE_SIZE = 40


@dataclass(frozen=True)
class FT001Discovery:
    """Discovery metadata returned by a WiFi controller."""

    host: str
    mac_address: str
    model_code: int
    local_name: str | None

    @property
    def is_ft001(self) -> bool:
        """Return true when the discovery model code matches FT001."""
        return self.model_code == FT001_MODEL_CODE


async def async_get_broadcast_addresses(hass: Any) -> list[str]:
    """Return IPv4 broadcast addresses configured in Home Assistant."""
    if hass is None:
        return [BROADCAST_ADDRESS]

    try:
        from homeassistant.components import network
    except ImportError:
        return [BROADCAST_ADDRESS]

    get_broadcasts = getattr(network, "async_get_ipv4_broadcast_addresses", None)
    if get_broadcasts is None:
        return [BROADCAST_ADDRESS]

    try:
        raw_addresses = await get_broadcasts(hass)
    except Exception:
        return [BROADCAST_ADDRESS]

    addresses = sorted({str(addr) for addr in raw_addresses if str(addr)})
    return addresses or [BROADCAST_ADDRESS]


async def async_discover_ft001(
    timeout: float = 3.0,
    address: str | None = None,
    addresses: Sequence[str] | None = None,
) -> list[FT001Discovery]:
    """Discover FT001-compatible controllers without blocking the event loop."""
    return await asyncio.to_thread(discover_ft001, timeout, address, addresses)


async def async_discover_ft001_host(
    host: str, timeout: float = 3.0
) -> FT001Discovery | None:
    """Return discovery metadata for one host when the device responds."""
    devices = await async_discover_ft001(timeout=timeout, address=host)
    for device in devices:
        if device.host == host:
            return device
    return devices[0] if len(devices) == 1 else None


def discover_ft001(
    timeout: float = 3.0,
    address: str | None = None,
    addresses: Sequence[str] | None = None,
) -> list[FT001Discovery]:
    """Discover FT001-compatible controllers with the SPNET UDP probe."""
    sock = _create_udp_socket()
    targets = _resolve_targets(address, addresses)
    unicast_target = address if addresses is None and address is not None else None
    quit_time = time.monotonic() + timeout
    responses: dict[str, FT001Discovery] = {}
    probe_interval = max(timeout / BROADCAST_FREQUENCY, 0.1)

    try:
        with selectors.DefaultSelector() as selector:
            selector.register(sock, selectors.EVENT_READ)
            while time.monotonic() < quit_time:
                sent_any = False
                for target in targets:
                    try:
                        sock.sendto(
                            SPNET_DISCOVERY_MESSAGE,
                            (target, SPNET_DISCOVERY_PORT),
                        )
                        sent_any = True
                    except OSError:
                        continue

                if not sent_any:
                    remaining = quit_time - time.monotonic()
                    if remaining <= 0:
                        break
                    selector.select(timeout=min(remaining, probe_interval))
                    continue

                while time.monotonic() < quit_time:
                    wait_time = min(
                        max(quit_time - time.monotonic(), 0),
                        probe_interval,
                    )
                    events = selector.select(timeout=wait_time)
                    if not events:
                        break

                    try:
                        data, from_address = sock.recvfrom(MAX_RESPONSE_SIZE)
                    except OSError:
                        continue

                    discovery = _parse_spnet_response(data, from_address)
                    if discovery is None:
                        continue
                    responses.setdefault(discovery.host, discovery)
                    if unicast_target is not None and discovery.host == unicast_target:
                        return list(responses.values())
    finally:
        sock.close()

    return list(responses.values())


def _resolve_targets(
    address: str | None, addresses: Sequence[str] | None
) -> list[str]:
    """Build a deduplicated list of UDP probe targets."""
    if addresses is not None:
        cleaned = list(dict.fromkeys(addr for addr in addresses if addr))
        if cleaned:
            return cleaned
    if address:
        return [address]
    return [BROADCAST_ADDRESS]


def _create_udp_socket() -> socket.socket:
    """Create a UDP socket for SPNET discovery."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Older controllers expect discovery requests to originate from 6454.
        sock.bind(("", SPNET_DISCOVERY_PORT))
    except OSError:
        sock.bind(("", 0))
    sock.setblocking(False)
    return sock


def _parse_spnet_response(
    data: bytes, from_address: tuple[str, int]
) -> FT001Discovery | None:
    """Parse one SPNET discovery response."""
    if data == SPNET_DISCOVERY_MESSAGE:
        return None
    if not data.startswith(SPNET_DISCOVERY_RESPONSE):
        return None

    payload = data[len(SPNET_DISCOVERY_RESPONSE) :]
    if len(payload) < 12:
        return None

    model_code = payload[3]
    mac_address = _format_mac(payload[5:11])
    name_length = payload[11]
    local_name = None
    if name_length:
        if len(payload) < 12 + name_length:
            return None
        raw_name = payload[12 : 12 + name_length]
        local_name = raw_name.decode("utf-8", errors="ignore").rstrip("\x00") or None

    return FT001Discovery(
        host=from_address[0],
        mac_address=mac_address,
        model_code=model_code,
        local_name=local_name,
    )


def _format_mac(raw: bytes) -> str:
    """Format raw MAC bytes as an uppercase Home Assistant identifier."""
    return ":".join(f"{value:02X}" for value in raw)
