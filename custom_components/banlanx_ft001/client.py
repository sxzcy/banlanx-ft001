"""Local TCP client for BanlanX FT001 fish tank lights."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

DEFAULT_PORT = 8587
HEADER = b"SPTECH\x00"
HEADER_SIZE = 13

CMD_STATUS_QUERY = 0x02
CMD_POWER = 0x50
CMD_STATIC_COLOR = 0x52


class BanlanxFT001Error(Exception):
    """Base error for FT001 communication."""


class BanlanxFT001ConnectionError(BanlanxFT001Error):
    """Raised when the controller cannot be reached."""


class BanlanxFT001ProtocolError(BanlanxFT001Error):
    """Raised when the controller returns an unexpected packet."""


@dataclass(frozen=True)
class FT001ChannelState:
    """State for one FT001 RGB output channel."""

    channel: int
    light_type: int
    power: bool
    mode: int
    effect: int
    brightness: int
    rgb: tuple[int, int, int]
    speed: int
    length: int


@dataclass(frozen=True)
class FT001Status:
    """Current FT001 device state."""

    firmware: str | None
    ssid: str | None
    ip_address: str | None
    channels: dict[int, FT001ChannelState]


class BanlanxFT001Client:
    """Client for the FT001 WiFi SPTECH protocol."""

    def __init__(
        self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.timeout = timeout

    async def async_get_status(self) -> FT001Status:
        """Fetch current device status."""
        header, payload = await self._async_request(CMD_STATUS_QUERY)
        if header[7] != CMD_STATUS_QUERY:
            raise BanlanxFT001ProtocolError("Unexpected status response command")
        return _parse_status_payload(payload)

    async def async_set_power(self, channel: int, state: bool) -> None:
        """Set one output channel on or off."""
        _validate_channel(channel)
        await self._async_send(CMD_POWER, bytes([channel, 0x01 if state else 0x00]))

    async def async_set_static_color(
        self, channel: int, rgb: tuple[int, int, int], brightness: int
    ) -> None:
        """Set one output channel to a static RGB color and brightness."""
        _validate_channel(channel)
        red, green, blue = (_validate_byte(value) for value in rgb)
        level = _validate_byte(brightness)
        await self._async_send(CMD_STATIC_COLOR, bytes([channel, red, green, blue, level]))

    async def _async_send(self, command: int, payload: bytes = b"") -> None:
        """Send a command that does not return a payload."""
        reader, writer = await self._async_open_connection()
        try:
            writer.write(_build_packet(command, payload))
            await writer.drain()
            await asyncio.sleep(0.1)
        finally:
            writer.close()
            await _async_wait_closed(writer)

    async def _async_request(self, command: int, payload: bytes = b"") -> tuple[bytes, bytes]:
        """Send a command and read an SPTECH response."""
        reader, writer = await self._async_open_connection()
        try:
            writer.write(_build_packet(command, payload))
            await writer.drain()
            header = await _async_read_exact(reader, HEADER_SIZE, self.timeout)
            _validate_response_header(header)
            payload_size = int.from_bytes(header[-2:], "big")
            response = await _async_read_exact(reader, payload_size, self.timeout)
            return header, response
        finally:
            writer.close()
            await _async_wait_closed(writer)

    async def _async_open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open a TCP connection to the controller."""
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except OSError as ex:
            raise BanlanxFT001ConnectionError(str(ex)) from ex
        except TimeoutError as ex:
            raise BanlanxFT001ConnectionError("Connection timed out") from ex


def _build_packet(command: int, payload: bytes = b"") -> bytes:
    """Build a network SPTECH packet."""
    return HEADER + bytes([command & 0xFF, 0x00, 0x00, 0x00]) + len(payload).to_bytes(2, "big") + payload


async def _async_read_exact(
    reader: asyncio.StreamReader, size: int, timeout: float
) -> bytes:
    """Read an exact byte count with a timeout."""
    try:
        return await asyncio.wait_for(reader.readexactly(size), timeout=timeout)
    except asyncio.IncompleteReadError as ex:
        raise BanlanxFT001ProtocolError(
            f"Expected {size} bytes, received {len(ex.partial)}"
        ) from ex
    except TimeoutError as ex:
        raise BanlanxFT001ConnectionError("Read timed out") from ex


async def _async_wait_closed(writer: asyncio.StreamWriter) -> None:
    """Wait for stream close when the runtime supports it."""
    try:
        await writer.wait_closed()
    except (AttributeError, OSError):
        return


def _validate_response_header(header: bytes) -> None:
    """Validate the fixed network response header."""
    if len(header) != HEADER_SIZE:
        raise BanlanxFT001ProtocolError("Invalid response header length")
    if not header.startswith(HEADER):
        raise BanlanxFT001ProtocolError("Invalid response header magic")


def _parse_status_payload(payload: bytes) -> FT001Status:
    """Parse the chunked FT001 status payload."""
    if not payload:
        raise BanlanxFT001ProtocolError("Empty status payload")

    length_fields = payload[0]
    offset = 1
    firmware: str | None = None
    ssid: str | None = None
    ip_address: str | None = None
    channels: dict[int, FT001ChannelState] = {}

    while offset < len(payload):
        if offset + 2 + length_fields > len(payload):
            raise BanlanxFT001ProtocolError("Truncated chunk header")
        chunk_type = payload[offset]
        size_start = offset + 1
        size_end = size_start + 1 + length_fields
        chunk_size = int.from_bytes(payload[size_start:size_end], "big")
        chunk_start = size_end
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(payload):
            raise BanlanxFT001ProtocolError("Truncated chunk payload")
        chunk = payload[chunk_start:chunk_end]

        if chunk_type == 1:
            firmware = _parse_firmware_chunk(chunk)
        elif chunk_type == 3:
            channel = _parse_channel_chunk(chunk)
            channels[channel.channel] = channel
        elif chunk_type == 6:
            ssid, ip_address = _parse_network_chunk(chunk)

        offset = chunk_end

    if not channels:
        raise BanlanxFT001ProtocolError("No output channels in status payload")

    return FT001Status(
        firmware=firmware,
        ssid=ssid,
        ip_address=ip_address,
        channels=channels,
    )


def _parse_firmware_chunk(chunk: bytes) -> str | None:
    """Parse firmware from chunk type 1."""
    if len(chunk) < 10:
        return None
    return chunk[2:10].decode("utf-8", errors="ignore").rstrip("\x00") or None


def _parse_network_chunk(chunk: bytes) -> tuple[str | None, str | None]:
    """Parse SSID and IP address from chunk type 6."""
    if len(chunk) < 2:
        return None, None
    string_count = int.from_bytes(chunk[0:2], "big")
    offset = 2
    values: list[str] = []
    for _ in range(string_count):
        if offset >= len(chunk):
            break
        size = chunk[offset]
        offset += 1
        values.append(chunk[offset : offset + size].decode("utf-8", errors="ignore"))
        offset += size
    return (
        values[0] if len(values) > 0 and values[0] else None,
        values[1] if len(values) > 1 and values[1] else None,
    )


def _parse_channel_chunk(chunk: bytes) -> FT001ChannelState:
    """Parse one FT001 output channel from chunk type 3."""
    if len(chunk) < 26:
        raise BanlanxFT001ProtocolError("Channel chunk is too short")
    channel = chunk[0]
    light_type = chunk[1]
    data = chunk[2:]
    return FT001ChannelState(
        channel=channel,
        light_type=light_type,
        power=bool(data[1]),
        mode=data[4],
        effect=data[5],
        brightness=data[7],
        rgb=(data[9], data[10], data[11]),
        speed=data[14],
        length=data[15],
    )


def _validate_channel(channel: int) -> None:
    """Validate FT001 channel number."""
    if channel not in (1, 2):
        raise ValueError("FT001 channel must be 1 or 2")


def _validate_byte(value: int) -> int:
    """Validate a byte value."""
    value = int(value)
    if value < 0 or value > 255:
        raise ValueError("Value must be between 0 and 255")
    return value
