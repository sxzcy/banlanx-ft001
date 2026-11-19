"""Unit tests covering audit fixes BLX-01..BLX-06 for BanlanX FT001."""

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
            unique_id="AA:BB:CC:DD:EE:FF",
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

        def _async_current_entries(self):
            return []

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self, updates=None):
            pass

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
        def __init__(self, id, connections=None):
            self.id = id
            self.connections = set(connections or set())

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
    ha_light.ATTR_RGB_COLOR = "rgb_color"

    class ColorMode:
        RGB = "rgb"

    class LightEntity:
        pass

    ha_light.ColorMode = ColorMode
    ha_light.LightEntity = LightEntity
    stubs["homeassistant.components.light"] = ha_light

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
    """Comprehensive tests for BLX-01..BLX-06."""

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
        cls.client_mod = importlib.import_module("custom_components.banlanx_ft001.client")
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
        cls.ha_ce = sys.modules["homeassistant.config_entries"]
        cls.ha_dr = sys.modules["homeassistant.helpers.device_registry"]
        cls.ha_exc = sys.modules["homeassistant.exceptions"]
        cls.ha_uc = sys.modules["homeassistant.helpers.update_coordinator"]

    @classmethod
    def tearDownClass(cls) -> None:
        for key in list(sys.modules):
            if key not in cls._saved_modules:
                sys.modules.pop(key, None)
        sys.modules.update(cls._saved_modules)

    def _sample_status(self, *, ch1_power: bool = False):
        ch1 = self.client_mod.FT001ChannelState(
            channel=1,
            light_type=5,
            power=ch1_power,
            mode=1,
            effect=1,
            brightness=120,
            rgb=(10, 20, 30),
            speed=3,
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
            speed=3,
            length=30,
        )
        return self.client_mod.FT001Status(
            firmware="V1.0.08",
            ssid="TestNet",
            ip_address="192.168.1.204",
            channels={1: ch1, 2: ch2},
        )

    def test_manifest_version_bumped(self) -> None:
        manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.4.1")

    # ---- BLX-01 ----
    def test_blx01_timeout_caught_before_oserror_with_non_empty_message(self) -> None:
        client = self.client_mod.BanlanxFT001Client("192.0.2.1", 8587, timeout=0.05)

        async def _run():
            # TimeoutError (subclass of OSError in Python 3.11+) -> "Connection timed out"
            with patch.object(
                self.client_mod.asyncio,
                "open_connection",
                new=AsyncMock(side_effect=TimeoutError()),
            ):
                with self.assertRaises(self.client_mod.BanlanxFT001ConnectionError) as ctx:
                    await client._async_open_connection()
                self.assertEqual(str(ctx.exception), "Connection timed out")

            # Empty OSError falls back to class name instead of empty string
            with patch.object(
                self.client_mod.asyncio,
                "open_connection",
                new=AsyncMock(side_effect=OSError()),
            ):
                with self.assertRaises(self.client_mod.BanlanxFT001ConnectionError) as ctx:
                    await client._async_open_connection()
                self.assertEqual(str(ctx.exception), "OSError")

            # Read timeout -> "Read timed out"
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
            unique_id="B4:14:CD:71:19:DF",
            data={
                "host": "192.168.1.204",
                "port": 8587,
                "name": "Tank",
                "mac_address": "B4:14:CD:71:19:DF",
            },
            options={"scan_interval": 15},
        )

        # OptionsFlowWithReload without custom __init__
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
            # async_setup_entry does NOT register add_update_listener
            with patch.object(
                self.client_mod.BanlanxFT001Client,
                "async_get_status",
                new=AsyncMock(return_value=self._sample_status()),
            ):
                ok = await self.pkg.async_setup_entry(hass, entry)
                self.assertTrue(ok)
            self.assertEqual(entry.update_listeners, [])

            # Options flow: host-only change schedules reload once; option change lets OptionsFlowWithReload reload
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
                        "host": "192.168.1.205",
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
                        "host": "192.168.1.205",
                        "port": 8587,
                        "name": "Tank",
                        "scan_interval": 30,
                    }
                )
                self.assertEqual(res2["type"], "create_entry")
                hass.config_entries.async_schedule_reload.assert_not_called()

        asyncio.run(_run())

    # ---- BLX-03 ----
    def test_blx03_device_registry_uses_new_api_and_new_connections(self) -> None:
        hass = _FakeHass()
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_reg",
            unique_id="B4:14:CD:71:19:DF",
            data={"mac_address": "B4:14:CD:71:19:DF"},
        )
        existing_device = self.ha_dr.DeviceEntry(
            id="dev_ft001",
            connections={("other", "abc")},
        )
        dr_mock = MagicMock()
        dr_mock.async_get_device_by_identifier.return_value = existing_device
        hass.device_registry = dr_mock

        self.pkg._async_update_device_registry(hass, entry)

        dr_mock.async_get_device_by_identifier.assert_called_once_with(
            (self.const.DOMAIN, "B4:14:CD:71:19:DF"),
            "entry_reg",
        )
        dr_mock.async_update_device.assert_called_once()
        _, kwargs = dr_mock.async_update_device.call_args
        self.assertIn("new_connections", kwargs)
        self.assertNotIn("merge_connections", kwargs)
        self.assertEqual(
            kwargs["new_connections"],
            {("other", "abc"), ("mac", "B4:14:CD:71:19:DF")},
        )

        # Fallback path when async_get_device_by_identifier does not exist
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
        self.assertEqual(legacy.called_with, {(self.const.DOMAIN, "B4:14:CD:71:19:DF")})
        self.assertIn("new_connections", legacy.updated[1])

    # ---- BLX-04 ----
    def test_blx04_discovery_uses_selectors_and_retries_sendto_oserror(self) -> None:
        self.assertFalse(hasattr(self.discovery_mod, "select"))
        self.assertIs(self.discovery_mod.selectors, selectors)

        response_pkt = bytes.fromhex(
            "53704e65740000210000000000010000139600b414cd7119df094654303031313944460100000000"
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
                return response_pkt, ("192.168.1.210", 6454)

            def close(self):
                pass

        select_calls = 0

        class _FakeSelector:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def register(self, sock, events):
                self.sock = sock

            def select(self, timeout=None):
                nonlocal select_calls
                select_calls += 1
                if sendto_calls >= 2:
                    return [(MagicMock(), selectors.EVENT_READ)]
                return []

        with (
            patch.object(self.discovery_mod, "_create_udp_socket", return_value=_FakeSocket()),
            patch.object(self.discovery_mod.selectors, "DefaultSelector", return_value=_FakeSelector()),
        ):
            found = self.discovery_mod.discover_ft001(timeout=1.0, address="192.168.1.210")

        self.assertEqual(sendto_calls, 2)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].host, "192.168.1.210")
        self.assertEqual(found[0].mac_address, "B4:14:CD:71:19:DF")

    def test_blx04_and_blx02_coordinator_cooldown_and_in_memory_host_update(self) -> None:
        hass = _FakeHass()
        entry = self.ha_ce.ConfigEntry(
            entry_id="entry_coord",
            data={"host": "192.168.1.10", "port": 8587, "mac_address": "B4:14:CD:71:19:DF"},
        )
        client = self.client_mod.BanlanxFT001Client("192.168.1.10", 8587)
        coord = self.coordinator_mod.BanlanxFT001Coordinator(hass, entry, client, "Tank")

        async def _run():
            # Discovery cooldown prevents repeated UDP broadcasts during continuous outage
            find_mock = AsyncMock(return_value=None)
            t = 1000.0
            with (
                patch.object(coord, "_async_find_discovery_by_mac", find_mock),
                patch.object(self.coordinator_mod.time, "monotonic", side_effect=lambda: t),
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

                # 60s later (< 300s cooldown) -> discovery skipped!
                t = 1060.0
                with self.assertRaises(self.ha_uc.UpdateFailed):
                    await coord._async_update_data()
                self.assertEqual(find_mock.await_count, 1)

                # 301s after first attempt -> discovery runs again!
                t = 1301.0
                with self.assertRaises(self.ha_uc.UpdateFailed):
                    await coord._async_update_data()
                self.assertEqual(find_mock.await_count, 2)

            # Host recovery updates self.client.host BEFORE persisting to ConfigEntry
            events: list[tuple[str, str]] = []

            def _record_update(target_entry, *, data):
                events.append(("update_entry", client.host))
                target_entry.data = data

            hass.config_entries.async_update_entry.side_effect = _record_update
            hass.config_entries.async_get_entry.return_value = entry

            recovered_discovery = self.discovery_mod.FT001Discovery(
                host="192.168.1.55",
                mac_address="B4:14:CD:71:19:DF",
                model_code=0x96,
                local_name="FT001",
            )
            coord._last_discovery_attempt = None
            with patch.object(
                coord,
                "_async_find_discovery_by_mac",
                new=AsyncMock(return_value=recovered_discovery),
            ):
                ok = await coord._async_recover_host()
            self.assertTrue(ok)
            self.assertEqual(client.host, "192.168.1.55")
            self.assertEqual(events, [("update_entry", "192.168.1.55")])

        asyncio.run(_run())

    # ---- BLX-05 ----
    def test_blx05_single_tcp_connection_and_power_on_when_state_none_and_errors(self) -> None:
        # 1. Client reuses ONE TCP connection for CMD_POWER + CMD_STATIC_COLOR
        client = self.client_mod.BanlanxFT001Client("192.168.1.204", 8587)
        written: list[bytes] = []
        open_count = 0
        close_count = 0

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
            return MagicMock(), _FakeWriter()

        async def _run():
            with (
                patch.object(client, "_async_open_connection", side_effect=_fake_open),
                patch.object(self.client_mod.asyncio, "sleep", new=AsyncMock()),
            ):
                await client.async_set_static_color(
                    1,
                    (10, 20, 30),
                    200,
                    power_on=True,
                )

            self.assertEqual(open_count, 1)
            self.assertEqual(close_count, 1)
            self.assertEqual(len(written), 2)
            self.assertEqual(written[0][7], self.client_mod.CMD_POWER)
            self.assertEqual(written[1][7], self.client_mod.CMD_STATIC_COLOR)

            # 2. LightEntity sets power_on=True when state is None or power is False, and False when already on
            hass = _FakeHass()
            entry = self.ha_ce.ConfigEntry(
                data={"host": "192.168.1.204", "port": 8587, "name": "Tank"},
            )
            coord = self.coordinator_mod.BanlanxFT001Coordinator(hass, entry, client, "Tank")
            coord.data = None  # state is None
            light = self.light_mod.BanlanxFT001Light(coord, entry, 1)

            with (
                patch.object(client, "async_set_static_color", new=AsyncMock()) as set_color,
                patch.object(coord, "async_request_refresh", new=AsyncMock()),
            ):
                await light.async_turn_on(brightness=128)
                set_color.assert_awaited_once_with(
                    1,
                    (255, 255, 255),
                    128,
                    power_on=True,
                )

                # state.power is False -> power_on=True
                set_color.reset_mock()
                coord.data = self._sample_status(ch1_power=False)
                await light.async_turn_on(rgb_color=(1, 2, 3))
                set_color.assert_awaited_once_with(
                    1,
                    (1, 2, 3),
                    120,
                    power_on=True,
                )

                # state.power is True -> power_on=False
                set_color.reset_mock()
                coord.data = self._sample_status(ch1_power=True)
                await light.async_turn_on(brightness=200)
                set_color.assert_awaited_once_with(
                    1,
                    (10, 20, 30),
                    200,
                    power_on=False,
                )

            # 3. LightEntity catches client errors -> HomeAssistantError
            with patch.object(
                client,
                "async_set_power",
                new=AsyncMock(side_effect=self.client_mod.BanlanxFT001ConnectionError("down")),
            ):
                with self.assertRaises(self.ha_exc.HomeAssistantError):
                    await light.async_turn_on()
                with self.assertRaises(self.ha_exc.HomeAssistantError):
                    await light.async_turn_off()

            with patch.object(
                client,
                "async_set_static_color",
                new=AsyncMock(side_effect=ValueError("bad byte")),
            ):
                with self.assertRaises(self.ha_exc.HomeAssistantError):
                    await light.async_turn_on(rgb_color=(300, 0, 0))

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
