"""Tests for FT001 UDP discovery parsing."""

from __future__ import annotations

DISCOVERY_RESPONSE_HEX = (
    "53704e65740000210000000000010000139600b414cd7119df094654303031313944460100000000"
)


def test_parse_spnet_response(component_modules):
    """Parse a known SPNET discovery response."""
    discovery = component_modules["discovery"]

    result = discovery._parse_spnet_response(
        bytes.fromhex(DISCOVERY_RESPONSE_HEX),
        ("192.168.1.204", discovery.SPNET_DISCOVERY_PORT),
    )

    assert result is not None
    assert result.host == "192.168.1.204"
    assert result.mac_address == "B4:14:CD:71:19:DF"
    assert result.model_code == 0x96
    assert result.local_name == "FT00119DF"
    assert result.is_ft001 is True


def test_parse_spnet_response_ignores_unknown_packet(component_modules):
    """Ignore packets that do not have the SPNET discovery prefix."""
    discovery = component_modules["discovery"]

    assert discovery._parse_spnet_response(b"not-spnet", ("192.168.1.204", 6454)) is None
