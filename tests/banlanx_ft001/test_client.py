"""Tests for the FT001 TCP protocol helpers."""

from __future__ import annotations

import pytest

STATUS_PAYLOAD_HEX = (
    "000111000856312e302e30380005010200580102061a00020643656c6c75720d3139322e"
    "3136382e312e3230340000be031e010501010000010101ff007facffffff031e010000ff"
    "0000000001000100031e020501010000010101ff00ff9ef3ffff031e010000ff00000000"
    "010001000d030100000d030200000c0c0100000000000000000000000c0c020000000000"
    "0000000000000a1c01000856312e302e3038000402010200580100002001c01009610005"
)


def test_parse_status_payload(component_modules):
    """Parse a known FT001 status payload."""
    client = component_modules["client"]
    status = client._parse_status_payload(bytes.fromhex(STATUS_PAYLOAD_HEX))

    assert status.firmware == "V1.0.08"
    assert status.ssid == "Cellur"
    assert status.ip_address == "192.168.1.204"
    assert sorted(status.channels) == [1, 2]

    channel_1 = status.channels[1]
    assert channel_1.light_type == 5
    assert channel_1.power is True
    assert channel_1.mode == 1
    assert channel_1.effect == 1
    assert channel_1.brightness == 255
    assert channel_1.rgb == (127, 172, 255)
    assert channel_1.speed == 3
    assert channel_1.length == 30

    channel_2 = status.channels[2]
    assert channel_2.light_type == 5
    assert channel_2.power is True
    assert channel_2.brightness == 255
    assert channel_2.rgb == (255, 158, 243)


def test_build_packet(component_modules):
    """Build a command packet with the SPTECH header and payload length."""
    client = component_modules["client"]

    packet = client._build_packet(client.CMD_POWER, b"\x01\x01")

    assert packet.hex() == "535054454348005000000000020101"


@pytest.mark.parametrize("value", [-1, 256])
def test_validate_byte_rejects_out_of_range(component_modules, value):
    """Reject values outside the byte range."""
    client = component_modules["client"]

    with pytest.raises(ValueError):
        client._validate_byte(value)


def test_validate_channel_rejects_unknown_channel(component_modules):
    """Reject channels outside the FT001 two-channel layout."""
    client = component_modules["client"]

    with pytest.raises(ValueError):
        client._validate_channel(3)
