"""Tests for the FT001 TCP protocol helpers."""

from __future__ import annotations

import pytest


def _chunk(chunk_type: int, body: bytes, length_fields: int = 0) -> bytes:
    """Build one TLV chunk matching the FT001 status payload format."""
    return (
        bytes([chunk_type])
        + len(body).to_bytes(1 + length_fields, "big")
        + body
    )


def _channel_body(
    channel: int,
    *,
    power: bool = True,
    mode: int = 1,
    effect: int = 1,
    brightness: int = 255,
    rgb: tuple[int, int, int] = (127, 172, 255),
    speed: int = 3,
    length: int = 30,
    effect_loop: bool = False,
    chip_order: int = 0,
) -> bytes:
    """Build a 30-byte channel status chunk matching FT001 firmware V1.0.08."""
    data = bytearray(28)
    data[0] = 1
    data[1] = 1 if power else 0
    data[2] = 1 if effect_loop else 0
    data[3] = chip_order
    data[4] = mode
    data[5] = effect
    data[6] = 1
    data[7] = brightness
    data[8] = 0
    data[9:12] = bytes(rgb)
    data[12:14] = b"\xff\xff"
    data[14] = speed
    data[15] = length
    data[16] = 1
    return bytes([channel, 5]) + bytes(data)


def _sample_status_payload() -> bytes:
    """Build a sanitized synthetic FT001 status payload."""
    fw_chunk = b"\x00\x08V1.0.08\x00\x05\x01\x02\x00\x58\x01\x02"
    ssid = b"TestWiFi"
    ip = b"192.0.2.10"
    net_chunk = (
        b"\x00\x02"
        + bytes([len(ssid)])
        + ssid
        + bytes([len(ip)])
        + ip
        + b"\x00\x00\xbe"
    )
    ch1 = _channel_body(1, rgb=(127, 172, 255), brightness=255, speed=3, length=30)
    ch2 = _channel_body(
        2, mode=3, effect=5, rgb=(255, 158, 243), brightness=180, speed=7, length=30
    )
    return (
        b"\x00"
        + _chunk(1, fw_chunk)
        + _chunk(6, net_chunk)
        + _chunk(3, ch1)
        + _chunk(3, ch2)
    )


def test_parse_status_payload(component_modules):
    """Parse a sanitized FT001 status payload."""
    client = component_modules["client"]
    status = client._parse_status_payload(_sample_status_payload())

    assert status.firmware == "V1.0.08"
    assert status.ssid == "TestWiFi"
    assert status.ip_address == "192.0.2.10"
    assert sorted(status.channels) == [1, 2]

    channel_1 = status.channels[1]
    assert channel_1.light_type == 5
    assert channel_1.power is True
    assert channel_1.mode == 1
    assert channel_1.effect == 1
    assert channel_1.effect_name == "Solid"
    assert channel_1.brightness == 255
    assert channel_1.rgb == (127, 172, 255)
    assert channel_1.speed == 3
    assert channel_1.length == 30

    channel_2 = status.channels[2]
    assert channel_2.light_type == 5
    assert channel_2.power is True
    assert channel_2.mode == 3
    assert channel_2.effect == 5
    assert channel_2.effect_name == "Gradient Seven Color"
    assert channel_2.brightness == 180
    assert channel_2.rgb == (255, 158, 243)
    assert channel_2.speed == 7


def test_parse_status_rejects_truncated_network_and_bad_length_fields(
    component_modules,
):
    """Reject malformed network strings and excessive length_fields headers."""
    client = component_modules["client"]

    truncated = bytes([1]) + _chunk(6, b"\x00\x01\x05ab", length_fields=1)
    with pytest.raises(client.BanlanxFT001ProtocolError):
        client._parse_status_payload(truncated)

    with pytest.raises(client.BanlanxFT001ProtocolError):
        client._parse_status_payload(bytes([9, 1, 0, 0]))


def test_build_packets_for_all_verified_commands(component_modules):
    """Build SPTECH packets for power, brightness, static color, effect, and speed."""
    client = component_modules["client"]

    assert (
        client._build_packet(client.CMD_POWER, b"\x01\x01").hex()
        == "535054454348005000000000020101"
    )
    assert (
        client._build_packet(client.CMD_BRIGHTNESS, b"\x01\x00\x80").hex()
        == "53505445434800510000000003010080"
    )
    assert (
        client._build_packet(client.CMD_EFFECT, b"\x02\x03\x05").hex()
        == "53505445434800530000000003020305"
    )
    assert (
        client._build_packet(client.CMD_SPEED, b"\x01\x06").hex()
        == "535054454348005400000000020106"
    )


@pytest.mark.parametrize("value", [-1, 256])
def test_validate_byte_rejects_out_of_range(component_modules, value):
    """Reject values outside the byte range."""
    client = component_modules["client"]

    with pytest.raises(ValueError):
        client._validate_byte(value)


@pytest.mark.parametrize("speed", [0, 11])
def test_validate_speed_rejects_out_of_range(component_modules, speed):
    """Reject speeds outside 1..10."""
    client = component_modules["client"]

    with pytest.raises(ValueError):
        client._validate_speed(speed)


def test_validate_channel_rejects_unknown_channel(component_modules):
    """Reject channels outside the FT001 two-channel layout."""
    client = component_modules["client"]

    with pytest.raises(ValueError):
        client._validate_channel(3)
