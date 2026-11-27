# BanlanX Aquarium Light for Home Assistant

Local WiFi Home Assistant custom integration for the BanlanX/SPLED `FT001`
aquarium light controller.

This integration communicates directly with the controller over your LAN. It
does not require BLE or any vendor cloud service.

## Verified Controller

- Model: `FT001`
- Model code: `150` / `0x96`
- Local name pattern: `FT001xxxx`
- Firmware: `V1.0.08`
- Protocol: TCP `SPTECH` on port `8587`, UDP/SPNET discovery on port `6454`
- Layout: two RGB PWM output channels (`light_type = 5`)

## Features

- Two Home Assistant RGB light entities, one per output channel
- Per-channel on/off, RGB color, standalone brightness, and 12 dynamic PWM RGB effects (`Solid` + dynamic modes)
- Two Home Assistant `number` entities for per-channel dynamic effect speed (`1–10`)
- Single-TCP-connection command + immediate state readback to reduce socket contention
- Automatic LAN discovery during setup (with manual IP fallback) using Home Assistant's configured IPv4 broadcast addresses
- Automatic IP recovery by MAC address on both polling and control connection failures (with 300s cooldown)
- Device registry MAC connection, firmware version, and display name sync
- Redacted config entry diagnostics
- Options flow for IP/host, port, display name, and polling interval (`5–300` seconds)

## Installation

### HACS Custom Repository

1. In HACS, open **Integrations**.
2. Add this repository as a custom repository with category **Integration**.
3. Install **BanlanX Aquarium Light**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & services -> Add integration** and search for
   **BanlanX Aquarium Light**.

### Manual

Copy this directory into your Home Assistant config directory:

```text
custom_components/banlanx_ft001
```

Then restart Home Assistant and add the integration from the UI.

## Configuration

When adding the integration, Home Assistant automatically scans your local
network for FT001 controllers over UDP `6454`. You can select a discovered
controller directly or choose manual setup with its IP address and port `8587`.

New entries use the discovered MAC address as the stable unique ID when the
controller answers the UDP discovery probe. Existing entries keep their current
unique ID so entity IDs do not unexpectedly change.

Use the integration options in Home Assistant to update:

- IP / host
- Port
- Display name
- Polling interval, from `5` to `300` seconds

## Supported Local Commands

- `0x02` — Status query
- `0x50` — Per-channel on/off (`[channel, state]`)
- `0x51` — Per-channel standalone color brightness (`[channel, 0x00, level]`)
- `0x52` — Per-channel static RGB color and brightness (`[channel, R, G, B, level]`)
- `0x53` — Per-channel mode and effect (`[channel, mode, effect]`)
- `0x54` — Per-channel dynamic effect speed (`[channel, speed]`, `1..10`)

## Development

Run the unit tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/banlanx_ft001 -q
```

Run a syntax check:

```bash
python -m compileall custom_components/banlanx_ft001
```

## Credits

The UDP discovery and BanlanX6xx command layouts were cross-checked against the
public UniLED implementation. All FT001 TCP status and control commands were
verified directly against a real FT001 controller on the LAN.
