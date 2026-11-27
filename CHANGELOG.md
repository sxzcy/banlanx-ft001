# Changelog

## 0.5.2

- Localize light effect names (`纯色常亮`, `七彩渐变`, `蓝色呼吸`, etc.) in `effect_list` while keeping backward-compatible English aliases for automations/service calls.

## 0.5.1

- Fix `manifest.json` category key to the valid Home Assistant category `lighting`.

## 0.5.0

- Add standalone brightness control (`0x51`) without leaving dynamic effects.
- Add static/dynamic effect selection (`0x53`, `Solid` plus 12 PWM RGB dynamic effects) on both light entities.
- Add per-channel effect speed sliders (`0x54`, `1..10`) via the `number` platform.
- Reuse a single TCP connection to send control commands and immediately read back updated state.
- Use Home Assistant `network` IPv4 broadcast addresses for reliable multi-subnet UDP discovery and IP recovery.
- Add automatic LAN discovery selection to the config flow (with manual IP fallback) and fix unique-ID IP update ordering.
- Trigger one-shot IP recovery on control connection failures and sync device name/firmware to the device registry.
- Add local HACS brand icons, align `strings.json` to English source copy, sanitize public test fixtures, and remove stray dev files from the component package.

## 0.4.1

- Fix `TimeoutError` shadowed by `OSError` producing empty error logs.
- Migrate to `OptionsFlowWithReload` and remove re-entrant update listener reloads on IP recovery.
- Replace deprecated `device_registry.async_get_device` / `merge_connections` calls with HA 2027.x-compatible APIs.
- Replace `select.select` with `selectors.DefaultSelector`, isolate `sendto` `OSError`, and add a 300s discovery cooldown.
- Send `CMD_POWER` + `CMD_STATIC_COLOR` over a single TCP connection and handle `state is None` safely.

## 0.4.0

- Add options flow for host, port, display name, and polling interval.
- Add config entry diagnostics.
- Add UDP/SPNET discovery metadata and IP recovery by MAC address.
- Add device registry MAC connection.
- Add two local RGB light entities for the verified FT001 two-channel layout.

## 0.1.0

- Initial local WiFi control for the BanlanX/SPLED FT001 controller.
