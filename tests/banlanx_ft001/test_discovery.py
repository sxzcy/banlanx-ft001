"""Tests for FT001 UDP discovery parsing and target resolution."""

from __future__ import annotations

import asyncio
from ipaddress import IPv4Address
import sys
import types

# Synthetic SPNET response: model=0x96, MAC=02:00:00:11:22:33, local_name=FT001DEMO
DISCOVERY_RESPONSE_HEX = (
    "53704e6574000021000000000001000013960002000011223309465430303144454d4f0100000000"
)


def test_parse_spnet_response(component_modules):
    """Parse a sanitized SPNET discovery response."""
    discovery = component_modules["discovery"]

    result = discovery._parse_spnet_response(
        bytes.fromhex(DISCOVERY_RESPONSE_HEX),
        ("192.0.2.10", discovery.SPNET_DISCOVERY_PORT),
    )

    assert result is not None
    assert result.host == "192.0.2.10"
    assert result.mac_address == "02:00:00:11:22:33"
    assert result.model_code == 0x96
    assert result.local_name == "FT001DEMO"
    assert result.is_ft001 is True


def test_parse_spnet_response_ignores_unknown_and_truncated_packets(
    component_modules,
):
    """Ignore packets without the SPNET prefix or with truncated local names."""
    discovery = component_modules["discovery"]

    assert (
        discovery._parse_spnet_response(b"not-spnet", ("192.0.2.10", 6454)) is None
    )
    truncated_name = bytes.fromhex(
        "53704e65740000210000000000010000139600020000112233094654"
    )
    assert (
        discovery._parse_spnet_response(truncated_name, ("192.0.2.10", 6454)) is None
    )


def test_resolve_targets_and_broadcast_helper(component_modules):
    """Resolve explicit broadcast lists and Home Assistant network broadcasts."""
    discovery = component_modules["discovery"]

    assert discovery._resolve_targets(None, None) == ["<broadcast>"]
    assert discovery._resolve_targets("192.0.2.10", None) == ["192.0.2.10"]
    assert discovery._resolve_targets(
        "192.0.2.10", ["192.0.2.255", "192.0.2.255", "198.51.100.255"]
    ) == ["192.0.2.255", "198.51.100.255"]

    ha_comp = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    ha_net = types.ModuleType("homeassistant.components.network")

    async def _fake_broadcasts(_hass):
        return {IPv4Address("198.51.100.255"), IPv4Address("192.0.2.255")}

    ha_net.async_get_ipv4_broadcast_addresses = _fake_broadcasts
    ha_comp.network = ha_net
    sys.modules["homeassistant.components.network"] = ha_net

    try:
        addrs = asyncio.run(discovery.async_get_broadcast_addresses(object()))
        assert addrs == ["192.0.2.255", "198.51.100.255"]
    finally:
        sys.modules.pop("homeassistant.components.network", None)
