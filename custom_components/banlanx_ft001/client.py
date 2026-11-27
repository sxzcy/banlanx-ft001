"""Local TCP client for BanlanX FT001 fish tank lights."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_PORT = 8587
HEADER = b"SPTECH\x00"
HEADER_SIZE = 13

CMD_STATUS_QUERY = 0x02
CMD_POWER = 0x50
CMD_BRIGHTNESS = 0x51
CMD_STATIC_COLOR = 0x52
CMD_EFFECT = 0x53
CMD_SPEED = 0x54

BRIGHTNESS_CHANNEL_COLOR = 0x00

MODE_STATIC_COLOR = 0x01
MODE_DYNAMIC_COLOR = 0x03

EFFECT_SOLID = "Solid"
FT001_DYNAMIC_EFFECTS: dict[int, str] = {
    0x01: "Jump Seven Color",
    0x02: "Breath Seven Color",
    0x03: "Strobe Seven Color",
    0x04: "Heartbeat Seven Color",
    0x05: "Gradient Seven Color",
    0x06: "Breath Red",
    0x07: "Breath Green",
    0x08: "Breath Blue",
    0x09: "Breath Yellow",
    0x0A: "Breath Cyan",
    0x0B: "Breath Purple",
    0x0C: "Breath White",
}
FT001_EFFECT_TO_COMMAND: dict[str, tuple[int, int]] = {
    EFFECT_SOLID: (MODE_STATIC_COLOR, 0x01),
    **{
        name: (MODE_DYNAMIC_COLOR, effect_code)
        for effect_code, name in FT001_DYNAMIC_EFFECTS.items()
    },
}
FT001_EFFECT_LIST: list[str] = list(FT001_EFFECT_TO_COMMAND)

MIN_SPEED = 1
MAX_SPEED = 10
MAX_LENGTH_FIELDS = 3


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
    effect_loop: bool = False
    chip_order: int = 0

    @property
    def effect_name(self) -> str | None:
        """Return the human-readable Home Assistant effect name."""
        if self.mode == MODE_STATIC_COLOR:
            return EFFECT_SOLID
        if self.mode == MODE_DYNAMIC_COLOR:
            return FT001_DYNAMIC_EFFECTS.get(self.effect)
        return None


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
        self._lock = asyncio.Lock()

    async def async_get_status(self) -> FT001Status:
        """Fetch current device status."""
        async with self._lock:
            header, payload = await self._async_request(CMD_STATUS_QUERY)
        if header[7] != CMD_STATUS_QUERY:
            raise BanlanxFT001ProtocolError("Unexpected status response command")
        return _parse_status_payload(payload)

    async def async_set_power(
        self,
        channel: int,
        state: bool,
        *,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Set one output channel on or off."""
        _validate_channel(channel)
        commands = [(CMD_POWER, bytes([channel, 0x01 if state else 0x00]))]
        async with self._lock:
            return await self._async_send_commands(commands, fetch_status=fetch_status)

    async def async_set_brightness(
        self,
        channel: int,
        brightness: int,
        *,
        power_on: bool = False,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Set brightness for one channel without leaving its current mode."""
        _validate_channel(channel)
        level = _validate_byte(brightness)
        commands: list[tuple[int, bytes]] = []
        if power_on:
            commands.append((CMD_POWER, bytes([channel, 0x01])))
        commands.append(
            (CMD_BRIGHTNESS, bytes([channel, BRIGHTNESS_CHANNEL_COLOR, level]))
        )
        async with self._lock:
            return await self._async_send_commands(commands, fetch_status=fetch_status)

    async def async_set_static_color(
        self,
        channel: int,
        rgb: tuple[int, int, int],
        brightness: int,
        *,
        power_on: bool = False,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Set one output channel to a static RGB color and brightness."""
        _validate_channel(channel)
        red, green, blue = (_validate_byte(value) for value in rgb)
        level = _validate_byte(brightness)
        commands: list[tuple[int, bytes]] = []
        if power_on:
            commands.append((CMD_POWER, bytes([channel, 0x01])))
        commands.append((CMD_STATIC_COLOR, bytes([channel, red, green, blue, level])))
        async with self._lock:
            return await self._async_send_commands(commands, fetch_status=fetch_status)

    async def async_set_effect(
        self,
        channel: int,
        effect: str,
        *,
        power_on: bool = False,
        brightness: int | None = None,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Set static or dynamic effect for one output channel."""
        _validate_channel(channel)
        if effect not in FT001_EFFECT_TO_COMMAND:
            raise ValueError(f"Unsupported FT001 effect: {effect}")
        mode, effect_code = FT001_EFFECT_TO_COMMAND[effect]
        commands: list[tuple[int, bytes]] = []
        if power_on:
            commands.append((CMD_POWER, bytes([channel, 0x01])))
        commands.append((CMD_EFFECT, bytes([channel, mode, effect_code])))
        if brightness is not None:
            level = _validate_byte(brightness)
            commands.append(
                (CMD_BRIGHTNESS, bytes([channel, BRIGHTNESS_CHANNEL_COLOR, level]))
            )
        async with self._lock:
            return await self._async_send_commands(commands, fetch_status=fetch_status)

    async def async_set_speed(
        self,
        channel: int,
        speed: int,
        *,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Set dynamic effect speed (1..10) for one output channel."""
        _validate_channel(channel)
        validated_speed = _validate_speed(speed)
        commands = [(CMD_SPEED, bytes([channel, validated_speed]))]
        async with self._lock:
            return await self._async_send_commands(commands, fetch_status=fetch_status)

    async def _async_send(self, command: int, payload: bytes = b"") -> None:
        """Send a command that does not return a payload."""
        await self._async_send_commands([(command, payload)])

    async def _async_send_commands(
        self,
        commands: Sequence[tuple[int, bytes]],
        *,
        fetch_status: bool = False,
    ) -> FT001Status | None:
        """Send one or more commands over a single TCP connection."""
        reader, writer = await self._async_open_connection()
        try:
            for command, payload in commands:
                await self._async_write_packet(writer, command, payload)
                await asyncio.sleep(0.1)
            if not fetch_status:
                return None
            header, response = await self._async_query_on_stream(
                reader, writer, CMD_STATUS_QUERY
            )
            if header[7] != CMD_STATUS_QUERY:
                raise BanlanxFT001ProtocolError("Unexpected status response command")
            return _parse_status_payload(response)
        finally:
            writer.close()
            await _async_wait_closed(writer)

    async def _async_request(
        self, command: int, payload: bytes = b""
    ) -> tuple[bytes, bytes]:
        """Send a command and read an SPTECH response."""
        reader, writer = await self._async_open_connection()
        try:
            return await self._async_query_on_stream(reader, writer, command, payload)
        finally:
            writer.close()
            await _async_wait_closed(writer)

    async def _async_query_on_stream(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        command: int,
        payload: bytes = b"",
    ) -> tuple[bytes, bytes]:
        """Send one request and read its SPTECH response on an open stream."""
        await self._async_write_packet(writer, command, payload)
        header = await _async_read_exact(reader, HEADER_SIZE, self.timeout)
        _validate_response_header(header)
        payload_size = int.from_bytes(header[-2:], "big")
        response = await _async_read_exact(reader, payload_size, self.timeout)
        return header, response

    async def _async_write_packet(
        self,
        writer: asyncio.StreamWriter,
        command: int,
        payload: bytes = b"",
    ) -> None:
        """Write and drain one SPTECH packet."""
        try:
            writer.write(_build_packet(command, payload))
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
        except TimeoutError as ex:
            raise BanlanxFT001ConnectionError("Write timed out") from ex
        except OSError as ex:
            raise BanlanxFT001ConnectionError(
                str(ex) or ex.__class__.__name__
            ) from ex

    async def _async_open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open a TCP connection to the controller."""
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except TimeoutError as ex:
            raise BanlanxFT001ConnectionError("Connection timed out") from ex
        except (OSError, ValueError) as ex:
            raise BanlanxFT001ConnectionError(
                str(ex) or ex.__class__.__name__
            ) from ex


def _build_packet(command: int, payload: bytes = b"") -> bytes:
    """Build a network SPTECH packet."""
    return (
        HEADER
        + bytes([command & 0xFF, 0x00, 0x00, 0x00])
        + len(payload).to_bytes(2, "big")
        + payload
    )


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
    except OSError as ex:
        raise BanlanxFT001ConnectionError(str(ex) or ex.__class__.__name__) from ex


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
    if length_fields > MAX_LENGTH_FIELDS:
        raise BanlanxFT001ProtocolError("Unsupported status chunk length field size")
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
        if offset + size > len(chunk):
            raise BanlanxFT001ProtocolError("Truncated network string")
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
        effect_loop=bool(data[2]),
        chip_order=data[3],
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


def _validate_speed(value: int) -> int:
    """Validate an FT001 dynamic effect speed value."""
    value = int(value)
    if value < MIN_SPEED or value > MAX_SPEED:
        raise ValueError(f"Speed must be between {MIN_SPEED} and {MAX_SPEED}")
    return value
