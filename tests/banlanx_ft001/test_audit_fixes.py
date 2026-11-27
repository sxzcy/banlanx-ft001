"""Comprehensive unit tests for BanlanX FT001 audit fixes and v0.5.0 features."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
import selectors
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
CUSTOM_COMPONENTS = ROOT / "custom_components"
INTEGRATION = CUSTOM_COMPONENTS / "banlanx_ft001"


def _build_ha_stubs() -> dict[str, types.ModuleType]:
    """Build lightweight Home Assistant & voluptuous stubs for local unittest runs."""
    stubs: dict[str, types.ModuleType] = {}

    if "voluptuous" not in sys.modules:
        try:
            importlib.import_module("voluptuous")
        except ImportError:
            vol = types.ModuleType("voluptuous")

            class _Marker:
                def __init__(self, key, default=None):
                    self.schema = key
                    self.default = default

                def __hash__(self):
                    return hash((type(self).__name__, self.schema))

                def __eq__(self, other):
                    return type(self) is type(other) and self.schema == other.schema

            class Required(_Marker):
                pass

            class Optional(_Marker):
                pass

            class Schema:
                def __init__(self, schema):
                    self.schema = schema

                def __call__(self, value):
                    return value

            vol.Required = Required
            vol.Optional = Optional
            vol.Schema = Schema
            vol.In = lambda container: container
            vol.All = lambda *validators: validators
            vol.Coerce = lambda fn: fn
            vol.Length = lambda **kwargs: kwargs
            vol.Range = lambda **kwargs: kwargs
            stubs["voluptuous"] = vol

    ha = types.ModuleType("homeassistant")
    stubs["homeassistant"] = ha

    ha_const = types.ModuleType("homeassistant.const")
    ha_const.CONF_HOST = "host"
    ha_const.CONF_NAME = "name"
    ha_const.CONF_PORT = "port"

    class Platform:
        LIGHT = "light"
        NUMBER = "number"

    ha_const.Platform = Platform
    stubs["homeassistant.const"] = ha_const

    ha_core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    ha_core.HomeAssistant = HomeAssistant
    stubs["homeassistant.core"] = ha_core

    ha_exc = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    ha_exc.HomeAssistantError = HomeAssistantError
    stubs["homeassistant.exceptions"] = ha_exc

    ha_def = types.ModuleType("homeassistant.data_entry_flow")

    class AbortFlow(Exception):
        def __init__(self, reason: str):
            super().__init__(reason)
            self.reason = reason

    ha_def.AbortFlow = AbortFlow
    ha_def.FlowResult = dict
    stubs["homeassistant.data_entry_flow"] = ha_def

    ha_ce = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(
            self,
            entry_id="entry_1",
            unique_id="02:00:00:11:22:33",
            data=None,
            options=None,
            title="FT001",
        ):
            self.entry_id = entry_id
            self.unique_id = unique_id
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.title = title
            self.runtime_data = None
            self.update_listeners = []

        def add_update_listener(self, listener):
            self.update_listeners.append(listener)
            return lambda: None

        def async_on_unload(self, func):
            return func

    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            cls.domain = domain

        def __init__(self):
            self.hass = None
            self._unique_id = None

        def _async_current_entries(self):
            return []

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self, updates=None):
            for entry in self._async_current_entries():
                if entry.unique_id == self._unique_id:
                    if updates:
                        entry.data.update(updates)
                    raise AbortFlow("already_configured")

        def async_show_form(self, *, step_id, data_schema=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(self, *, title, data, options=None):
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "options": options,
            }

    class OptionsFlow:
        def __init__(self):
            self._ha_config_entry = None
            self.hass = None

        @property
        def config_entry(self):
            return self._ha_config_entry

        def async_show_form(self, *, step_id, data_schema=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

    class OptionsFlowWithReload(OptionsFlow):
        pass

    ha_ce.ConfigEntry = ConfigEntry
    ha_ce.ConfigFlow = ConfigFlow
    ha_ce.OptionsFlow = OptionsFlow
    ha_ce.OptionsFlowWithReload = OptionsFlowWithReload
    ha.config_entries = ha_ce
    stubs["homeassistant.config_entries"] = ha_ce

    ha_helpers = types.ModuleType("homeassistant.helpers")
    stubs["homeassistant.helpers"] = ha_helpers

    ha_dr = types.ModuleType("homeassistant.helpers.device_registry")
    ha_dr.CONNECTION_NETWORK_MAC = "mac"

    class DeviceEntry:
        def __init__(self, id, connections=None, name=None, sw_version=None):
            self.id = id
            self.connections = set(connections or set())
            self.name = name
            self.sw_version = sw_version

    ha_dr.DeviceEntry = DeviceEntry
    ha_dr.async_get = lambda hass: hass.device_registry
    ha_helpers.device_registry = ha_dr
    stubs["homeassistant.helpers.device_registry"] = ha_dr

    ha_ep = types.ModuleType("homeassistant.helpers.entity_platform")
    ha_ep.AddEntitiesCallback = object
    stubs["homeassistant.helpers.entity_platform"] = ha_ep

    ha_uc = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, *, name, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True

        async def async_config_entry_first_refresh(self):
            self.data = await self._async_update_data()

        async def async_request_refresh(self):
            pass

        def async_set_updated_data(self, data):
            self.data = data
            self.last_update_success = True

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return self.coordinator.last_update_success

    ha_uc.UpdateFailed = UpdateFailed
    ha_uc.DataUpdateCoordinator = DataUpdateCoordinator
    ha_uc.CoordinatorEntity = CoordinatorEntity
    stubs["homeassistant.helpers.update_coordinator"] = ha_uc

    ha_comp = types.ModuleType("homeassistant.components")
    stubs["homeassistant.components"] = ha_comp

    ha_light = types.ModuleType("homeassistant.components.light")
    ha_light.ATTR_BRIGHTNESS = "brightness"
    ha_light.ATTR_EFFECT = "effect"
    ha_light.ATTR_RGB_COLOR = "rgb_color"

    class ColorMode:
        RGB = "rgb"

    class LightEntityFeature:
        EFFECT = 4

    class LightEntity:
        @property
        def device_info(self):
            return getattr(self, "_attr_device_info", None)

        @property
        def effect_list(self):
            return getattr(self, "_attr_effect_list", None)

    ha_light.ColorMode = ColorMode
    ha_light.LightEntityFeature = LightEntityFeature
    ha_light.LightEntity = LightEntity
    stubs["homeassistant.components.light"] = ha_light

    ha_number = types.ModuleType("homeassistant.components.number")

    class NumberMode:
        SLIDER = "slider"

    class NumberEntity:
        pass

    ha_number.NumberMode = NumberMode
    ha_number.NumberEntity = NumberEntity
    stubs["homeassistant.components.number"] = ha_number

    ha_diag = types.ModuleType("homeassistant.components.diagnostics")

    def async_redact_data(data, to_redact):
        if isinstance(data, dict):
            return {
                k: "**REDACTED**" if k in to_redact else async_redact_data(v, to_redact)
                for k, v in data.items()
            }
        return data

    ha_diag.async_redact_data = async_redact_data
    stubs["homeassistant.components.diagnostics"] = ha_diag

    cc = types.ModuleType("custom_components")
    cc.__path__ = [str(CUSTOM_COMPONENTS)]
    stubs["custom_components"] = cc

    return stubs


class _FakeHass:
    def __init__(self):
        self.device_registry = None
        self.config_entries = MagicMock()
        self.config_entries.async_forward_entry_setups = AsyncMock()
        self.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.config_entries.async_reload = AsyncMock()
        self.config_entries.async_entries.return_value = []


class BanlanxAuditFixesTest(unittest.TestCase):
    """Comprehensive tests covering BLX-01..BLX-06 and v0.5.0 local features."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_modules = dict(sys.modules)
        stubs = _build_ha_stubs()
        for name, mod in stubs.items():
            sys.modules[name] = mod
        for key in list(sys.modules):
            if key == "custom_components.banlanx_ft001" or key.startswith(
                "custom_components.banlanx_ft001."
            ):
                sys.modules.pop(key, None)

        cls.pkg = importlib.import_module("custom_components.banlanx_ft001")
        cls.const = importlib.import_module("custom_components.banlanx_ft001.const")
        cls.client_mod = importlib.import_module(
            "custom_components.banlanx_ft001.client"
        )
        cls.discovery_mod = importlib.import_module(
            "custom_components.banlanx_ft001.discovery"
        )
        cls.coordinator_mod = importlib.import_module(
            "custom_components.banlanx_ft001.coordinator"
        )
        cls.config_flow_mod = importlib.import_module(
            "custom_components.banlanx_ft001.config_flow"
        )
        cls.light_mod = importlib.import_module("custom_components.banlanx_ft001.light")
        cls.number_mod = importlib.import_module(
            "custom_components.banlanx_ft001.number"
        )
        cls.diagnostics_mod = importlib.import_module(
            "custom_components.banlanx_ft001.diagnostics"
        )
        cls.ha_ce = sys.modules["homeassistant.config_entries"]
        cls.ha_def = sys.modules["homeassistant.data_entry_flow"]
        cls.ha_dr = sys.modules["homeassistant.helpers.device_registry"]
        cls.ha_exc = sys.modules["homeassistant.exceptions"]
        cls.ha_uc = sys.modules["homeassistant.helpers.update_coordinator"]

    @classmethod
    def tearDownClass(cls) -> None:
        for key in list(sys.modules):
            if key not in cls._saved_modules:
                sys.modules.pop(key, None)
        sys.modules.update(cls._saved_modules)

    def _sample_status(
        self,
        *,
        ch1_power: bool = False,
        ch1_mode: int = 1,
        ch1_effect: int = 1,
        ch1_speed: int = 3,
    ):
        ch1 = self.client_mod.FT001ChannelState(
            channel=1,
            light_type=5,
            power=ch1_power,
            mode=ch1_mode,
            effect=ch1_effect,
            brightness=120,
            rgb=(10, 20, 30),
            speed=ch1_speed,
            length=30,
        )
        ch2 = self.client_mod.FT001ChannelState(
            channel=2,
            light_type=5,
            power=True,
            mode=1,
            effect=1,
            brightness=255,
            rgb=(40, 50, 60),
            speed=6,
            length=30,
        )
        return self.client_mod.FT001Status(
            firmware="V1.0.08",
            ssid="TestNet",
            ip_address="192.0.2.10",
            channels={1: ch1, 2: ch2},
        )

    def test_manifest_version_bumped(self) -> None:
        manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.5.2")

    # ---- BLX-01 ----
    def test_blx01_timeout_caught_before_oserror_with_non_empty_message(self) -> None:
        client = self.client_mod.BanlanxFT001Client("192.0.2.1", 8587, timeout=0.05)

        async def _run():
            with patch.object(
                self.client_mod.asyncio,
                "open_connection",
                new=AsyncMock(side_effect=TimeoutError()),
            ):
                with self.assertRaises(self.client_mod.BanlanxFT001ConnectionError) as ctx:
                    await client._async_open_connection()
                self.assertEqual(str(ctx.exception), "Connection timed out")

            with patch.object(
                self.client_mod.asyncio,
                "open_connection",
                new=AsyncMock(side_effect=OSError()),
            ):
                with self.assertRaises(self.client_mod.BanlanxFT001ConnectionError) as ctx:
                    await client._async_open_connection()
                self.assertEqual(str(ctx.exception), "OSError")

            fake_reader = MagicMock()
            fake_reader.readexactly = AsyncMock(side_effect=TimeoutError())
            with self.assertRaises(self.client_mod.BanlanxFT001ConnectionError) as ctx:
                await self.client_mod._async_read_exact(fake_reader, 13, 0.05)
            self.assertEqual(str(ctx.exception), "Read timed out")

        asyncio.run(_run())

    # ---- BLX-02 & BLX-06 ----
    def test_blx02_blx06_options_flow_with_reload_and_no_update_listener(self) -> None:
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_ft001",
            unique_id="02:00:00:11:22:33",
            data={
                "host": "192.0.2.10",
                "port": 8587,
                "name": "Tank",
                "mac_address": "02:00:00:11:22:33",
            },
            options={"scan_interval": 15},
        )

        opt_flow = self.config_flow_mod.BanlanxFT001ConfigFlow.async_get_options_flow(entry)
        self.assertIsInstance(opt_flow, self.ha_ce.OptionsFlowWithReload)
        self.assertNotIn("__init__", self.config_flow_mod.BanlanxFT001OptionsFlow.__dict__)

        hass = _FakeHass()
        dr_mock = MagicMock()
        dr_mock.async_get_device_by_identifier.return_value = self.ha_dr.DeviceEntry(
            id="dev_1",
            connections=set(),
        )
        hass.device_registry = dr_mock

        async def _run():
            with patch.object(
                self.client_mod.BanlanxFT001Client,
                "async_get_status",
                new=AsyncMock(return_value=self._sample_status()),
            ):
                ok = await self.pkg.async_setup_entry(hass, entry)
                self.assertTrue(ok)
            self.assertEqual(entry.update_listeners, [])

            opt_flow.hass = hass
            opt_flow._ha_config_entry = entry
            hass.config_entries.async_update_entry.return_value = True
            with (
                patch.object(
                    self.client_mod.BanlanxFT001Client,
                    "async_get_status",
                    new=AsyncMock(return_value=self._sample_status()),
                ),
                patch.object(
                    self.config_flow_mod,
                    "_async_get_verified_discovery",
                    new=AsyncMock(return_value=None),
                ),
            ):
                res = await opt_flow.async_step_init(
                    {
                        "host": "192.0.2.11",
                        "port": 8587,
                        "name": "Tank",
                        "scan_interval": 15,
                    }
                )
                self.assertEqual(res["type"], "create_entry")
                hass.config_entries.async_schedule_reload.assert_called_once_with(
                    "entry_ft001"
                )

                hass.config_entries.async_schedule_reload.reset_mock()
                res2 = await opt_flow.async_step_init(
                    {
                        "host": "192.0.2.11",
                        "port": 8587,
                        "name": "Tank",
                        "scan_interval": 30,
                    }
                )
                self.assertEqual(res2["type"], "create_entry")
                hass.config_entries.async_schedule_reload.assert_not_called()

        asyncio.run(_run())

    # ---- BLX-03 + device name & firmware sync ----
    def test_blx03_device_registry_uses_new_api_and_syncs_name_firmware(self) -> None:
        hass = _FakeHass()
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_reg",
            unique_id="02:00:00:11:22:33",
            data={"mac_address": "02:00:00:11:22:33", "name": "Reef Tank"},
        )
        coord = MagicMock()
        coord.data = self._sample_status()
        entry.runtime_data = coord

        existing_device = self.ha_dr.DeviceEntry(
            id="dev_ft001",
            connections={("other", "abc")},
            name="Old Tank",
            sw_version="V1.0.00",
        )
        dr_mock = MagicMock()
        dr_mock.async_get_device_by_identifier.return_value = existing_device
        hass.device_registry = dr_mock

        self.pkg._async_update_device_registry(hass, entry)

        dr_mock.async_get_device_by_identifier.assert_called_once_with(
            (self.const.DOMAIN, "02:00:00:11:22:33"),
            "entry_reg",
        )
        dr_mock.async_update_device.assert_called_once()
        _, kwargs = dr_mock.async_update_device.call_args
        self.assertIn("new_connections", kwargs)
        self.assertNotIn("merge_connections", kwargs)
        self.assertEqual(
            kwargs["new_connections"],
            {("other", "abc"), ("mac", "02:00:00:11:22:33")},
        )
        self.assertEqual(kwargs["name"], "Reef Tank")
        self.assertEqual(kwargs["sw_version"], "V1.0.08")

        class _LegacyRegistry:
            def __init__(self):
                self.called_with = None
                self.updated = None

            def async_get_device(self, *, identifiers):
                self.called_with = identifiers
                return existing_device

            def async_update_device(self, device_id, **kw):
                self.updated = (device_id, kw)

        legacy = _LegacyRegistry()
        hass.device_registry = legacy
        self.pkg._async_update_device_registry(hass, entry)
        self.assertEqual(legacy.called_with, {(self.const.DOMAIN, "02:00:00:11:22:33")})
        self.assertIn("new_connections", legacy.updated[1])

    # ---- BLX-04 ----
    def test_blx04_discovery_uses_selectors_and_retries_sendto_oserror(self) -> None:
        self.assertFalse(hasattr(self.discovery_mod, "select"))
        self.assertIs(self.discovery_mod.selectors, selectors)

        response_pkt = bytes.fromhex(
            "53704e6574000021000000000001000013960002000011223309465430303144454d4f0100000000"
        )
        sendto_calls = 0

        class _FakeSocket:
            def sendto(self, data, addr):
                nonlocal sendto_calls
                sendto_calls += 1
                if sendto_calls == 1:
                    raise OSError("transient network down")
                return len(data)

            def recvfrom(self, size):
                return response_pkt, ("192.0.2.20", 6454)

            def close(self):
                pass

        class _FakeSelector:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def register(self, sock, events):
                self.sock = sock

            def select(self, timeout=None):
                if sendto_calls >= 2:
                    return [(MagicMock(), selectors.EVENT_READ)]
                return []

        with (
            patch.object(
                self.discovery_mod, "_create_udp_socket", return_value=_FakeSocket()
            ),
            patch.object(
                self.discovery_mod.selectors,
                "DefaultSelector",
                return_value=_FakeSelector(),
            ),
        ):
            found = self.discovery_mod.discover_ft001(timeout=1.0, address="192.0.2.20")

        self.assertEqual(sendto_calls, 2)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].host, "192.0.2.20")
        self.assertEqual(found[0].mac_address, "02:00:00:11:22:33")

    def test_blx04_and_blx02_coordinator_cooldown_and_command_recovery(self) -> None:
        hass = _FakeHass()
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_coord",
            data={"host": "192.0.2.10", "port": 8587, "mac_address": "02:00:00:11:22:33"},
        )
        client = self.client_mod.BanlanxFT001Client("192.0.2.10", 8587)
        coord = self.coordinator_mod.BanlanxFT001Coordinator(hass, entry, client, "Tank")

        async def _run():
            find_mock = AsyncMock(return_value=None)
            t = 1000.0
            with (
                patch.object(coord, "_async_find_discovery_by_mac", find_mock),
                patch.object(
                    self.coordinator_mod.time, "monotonic", side_effect=lambda: t
                ),
                patch.object(
                    client,
                    "async_get_status",
                    new=AsyncMock(
                        side_effect=self.client_mod.BanlanxFT001ConnectionError("offline")
                    ),
                ),
            ):
                with self.assertRaises(self.ha_uc.UpdateFailed):
                    await coord._async_update_data()
                self.assertEqual(find_mock.await_count, 1)

                t = 1060.0
                with self.assertRaises(self.ha_uc.UpdateFailed):
                    await coord._async_update_data()
                self.assertEqual(find_mock.await_count, 1)

                t = 1301.0
                with self.assertRaises(self.ha_uc.UpdateFailed):
                    await coord._async_update_data()
                self.assertEqual(find_mock.await_count, 2)

            # Control command triggers immediate IP recovery and syncs returned status
            events: list[tuple[str, str]] = []

            def _record_update(target_entry, *, data):
                events.append(("update_entry", client.host))
                target_entry.data = data

            hass.config_entries.async_update_entry.side_effect = _record_update
            hass.config_entries.async_get_entry.return_value = entry

            recovered_discovery = self.discovery_mod.FT001Discovery(
                host="192.0.2.55",
                mac_address="02:00:00:11:22:33",
                model_code=0x96,
                local_name="FT001DEMO",
            )
            coord._last_discovery_attempt = None
            new_status = self._sample_status(ch1_power=True)
            attempts = 0

            async def _flaky_action():
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise self.client_mod.BanlanxFT001ConnectionError("stale ip")
                return new_status

            with patch.object(
                coord,
                "_async_find_discovery_by_mac",
                new=AsyncMock(return_value=recovered_discovery),
            ):
                await coord.async_execute_command(_flaky_action)

            self.assertEqual(attempts, 2)
            self.assertEqual(client.host, "192.0.2.55")
            self.assertEqual(events, [("update_entry", "192.0.2.55")])
            self.assertIs(coord.data, new_status)

        asyncio.run(_run())

    # ---- BLX-05 + v0.5.0 single-TCP readback, brightness, effects, speed ----
    def test_blx05_and_v050_single_tcp_readback_light_and_number(self) -> None:
        client = self.client_mod.BanlanxFT001Client("192.0.2.10", 8587)
        written: list[bytes] = []
        open_count = 0
        close_count = 0

        # Build a valid response packet for CMD_STATUS_QUERY readback
        ch_body = bytearray(28)
        ch_body[1] = 1
        ch_body[4] = 3
        ch_body[5] = 5
        ch_body[7] = 200
        ch_body[9:12] = bytes((10, 20, 30))
        ch_body[14] = 8
        ch_body[15] = 30
        ch1 = b"\x01\x05" + bytes(ch_body)
        status_payload = b"\x00" + b"\x03" + bytes([len(ch1)]) + ch1
        status_packet = self.client_mod._build_packet(
            self.client_mod.CMD_STATUS_QUERY, status_payload
        )

        class _FakeReader:
            def __init__(self, buf: bytes):
                self._buf = bytearray(buf)

            async def readexactly(self, n: int) -> bytes:
                out = bytes(self._buf[:n])
                del self._buf[:n]
                return out

        class _FakeWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

            def close(self) -> None:
                nonlocal close_count
                close_count += 1

            async def wait_closed(self) -> None:
                pass

        async def _fake_open():
            nonlocal open_count
            open_count += 1
            return _FakeReader(status_packet), _FakeWriter()

        async def _run():
            with (
                patch.object(client, "_async_open_connection", side_effect=_fake_open),
                patch.object(self.client_mod.asyncio, "sleep", new=AsyncMock()),
            ):
                st = await client.async_set_effect(
                    1,
                    "Gradient Seven Color",
                    power_on=True,
                    brightness=200,
                    fetch_status=True,
                )

            self.assertEqual(open_count, 1)
            self.assertEqual(close_count, 1)
            self.assertEqual(
                [pkt[7] for pkt in written],
                [
                    self.client_mod.CMD_POWER,
                    self.client_mod.CMD_EFFECT,
                    self.client_mod.CMD_BRIGHTNESS,
                    self.client_mod.CMD_STATUS_QUERY,
                ],
            )
            self.assertIsNotNone(st)
            self.assertEqual(st.channels[1].effect_name, "七彩渐变")
            self.assertEqual(st.channels[1].speed, 8)

            # Light entity routing: brightness-only uses CMD_BRIGHTNESS, effect uses CMD_EFFECT
            hass = _FakeHass()
            entry = self.ha_ce.ConfigEntry(
                data={"host": "192.0.2.10", "port": 8587, "name": "Tank"},
            )
            coord = self.coordinator_mod.BanlanxFT001Coordinator(
                hass, entry, client, "Tank"
            )
            coord.data = self._sample_status(
                ch1_power=True, ch1_mode=3, ch1_effect=5, ch1_speed=4
            )
            light = self.light_mod.BanlanxFT001Light(coord, entry, 1)
            self.assertEqual(light.effect, "七彩渐变")
            self.assertEqual(light.device_info["sw_version"], "V1.0.08")
            self.assertIn("纯色常亮", light.effect_list)
            self.assertIn("七彩渐变", light.effect_list)

            with (
                patch.object(
                    client, "async_set_brightness", new=AsyncMock(return_value=coord.data)
                ) as set_bri,
                patch.object(
                    client, "async_set_effect", new=AsyncMock(return_value=coord.data)
                ) as set_fx,
                patch.object(
                    client,
                    "async_set_static_color",
                    new=AsyncMock(return_value=coord.data),
                ) as set_color,
            ):
                await light.async_turn_on(brightness=128)
                set_bri.assert_awaited_once_with(
                    1, 128, power_on=False, fetch_status=True
                )
                set_color.assert_not_awaited()

                await light.async_turn_on(effect="蓝色呼吸")
                set_fx.assert_awaited_once_with(
                    1, "蓝色呼吸", power_on=False, brightness=None, fetch_status=True
                )

                await light.async_turn_on(rgb_color=(1, 2, 3))
                set_color.assert_awaited_once_with(
                    1, (1, 2, 3), 120, power_on=False, fetch_status=True
                )

            # Number entity for dynamic effect speed
            speed_num = self.number_mod.BanlanxFT001SpeedNumber(coord, entry, 1)
            self.assertEqual(speed_num.native_value, 4.0)
            self.assertTrue(speed_num.available)
            with patch.object(
                client, "async_set_speed", new=AsyncMock(return_value=coord.data)
            ) as set_speed:
                await speed_num.async_set_native_value(9.0)
                set_speed.assert_awaited_once_with(1, 9, fetch_status=True)

            with patch.object(
                client,
                "async_set_speed",
                new=AsyncMock(
                    side_effect=self.client_mod.BanlanxFT001ConnectionError("down")
                ),
            ):
                with self.assertRaises(self.ha_exc.HomeAssistantError):
                    await speed_num.async_set_native_value(5.0)

        asyncio.run(_run())

    # ---- ConfigFlow auto-discovery + unique_id IP update ordering ----
    def test_config_flow_discovery_and_unique_id_update(self) -> None:
        flow = self.config_flow_mod.BanlanxFT001ConfigFlow()
        flow.hass = _FakeHass()
        found = self.discovery_mod.FT001Discovery(
            host="192.0.2.30",
            mac_address="02:00:00:11:22:33",
            model_code=0x96,
            local_name="FT001DEMO",
        )

        async def _run():
            with (
                patch.object(
                    self.config_flow_mod,
                    "async_get_broadcast_addresses",
                    new=AsyncMock(return_value=["192.0.2.255"]),
                ),
                patch.object(
                    self.config_flow_mod,
                    "async_discover_ft001",
                    new=AsyncMock(return_value=[found]),
                ),
            ):
                step = await flow.async_step_user()
                self.assertEqual(step["type"], "form")
                self.assertEqual(step["step_id"], "discover")

            # Selecting discovered device validates and creates entry
            with patch.object(
                self.client_mod.BanlanxFT001Client,
                "async_get_status",
                new=AsyncMock(return_value=self._sample_status()),
            ):
                created = await flow.async_step_discover(
                    {"device": "192.0.2.30", "name": "My Tank"}
                )
                self.assertEqual(created["type"], "create_entry")
                self.assertEqual(created["data"]["host"], "192.0.2.30")
                self.assertEqual(created["data"]["mac_address"], "02:00:00:11:22:33")

            # Existing entry with same MAC gets host updated before AbortFlow
            existing = self.ha_ce.ConfigEntry(
                entry_id="existing_1",
                unique_id="02:00:00:11:22:33",
                data={
                    "host": "192.0.2.10",
                    "port": 8587,
                    "mac_address": "02:00:00:11:22:33",
                },
            )
            flow2 = self.config_flow_mod.BanlanxFT001ConfigFlow()
            flow2.hass = _FakeHass()
            flow2._async_current_entries = lambda: [existing]
            with (
                patch.object(
                    self.client_mod.BanlanxFT001Client,
                    "async_get_status",
                    new=AsyncMock(return_value=self._sample_status()),
                ),
                patch.object(
                    self.config_flow_mod,
                    "_async_get_verified_discovery",
                    new=AsyncMock(return_value=found),
                ),
            ):
                with self.assertRaises(self.ha_def.AbortFlow) as ctx:
                    await flow2.async_step_user(
                        {"host": "192.0.2.30", "port": 8587, "name": "Tank"}
                    )
                self.assertEqual(ctx.exception.reason, "already_configured")
                self.assertEqual(existing.data["host"], "192.0.2.30")

        asyncio.run(_run())

    # ---- Diagnostics redaction ----
    def test_diagnostics_redacts_network_and_handles_missing_runtime_data(self) -> None:
        hass = _FakeHass()
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_diag",
            unique_id="02:00:00:11:22:33",
            data={
                "host": "192.0.2.10",
                "port": 8587,
                "name": "Tank",
                "mac_address": "02:00:00:11:22:33",
                "local_name": "FT001DEMO",
                "model_code": 0x96,
            },
        )

        async def _run():
            # When runtime_data is None
            res_empty = await self.diagnostics_mod.async_get_config_entry_diagnostics(
                hass, entry
            )
            self.assertEqual(res_empty["entry"]["host"], "**REDACTED**")
            self.assertEqual(res_empty["entry"]["mac_address"], "**REDACTED**")
            self.assertEqual(res_empty["entry"]["unique_id"], "**REDACTED**")
            self.assertNotIn("status", res_empty)

            # When coordinator has status
            client = self.client_mod.BanlanxFT001Client("192.0.2.10", 8587)
            coord = self.coordinator_mod.BanlanxFT001Coordinator(
                hass, entry, client, "Tank"
            )
            coord.data = self._sample_status(ch1_power=True)
            entry.runtime_data = coord

            res_full = await self.diagnostics_mod.async_get_config_entry_diagnostics(
                hass, entry
            )
            self.assertEqual(res_full["client_host"], "**REDACTED**")
            self.assertEqual(res_full["status"]["ssid"], "**REDACTED**")
            self.assertEqual(res_full["status"]["ip_address"], "**REDACTED**")
            self.assertEqual(res_full["status"]["firmware"], "V1.0.08")
            self.assertIn(1, res_full["status"]["channels"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
