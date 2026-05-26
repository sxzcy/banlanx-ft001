# BanlanX Aquarium Light for Home Assistant

Local WiFi Home Assistant custom integration for the BanlanX/SPLED `FT001`
fish tank light controller.

This integration talks to the controller directly on the LAN. It does not use
BLE or a vendor cloud service.

## Verified Controller

- Model: `FT001`
- Model code: `150` / `0x96`
- Local name: `FT00119DF`
- Firmware: `V1.0.08`
- Protocol: TCP `SPTECH` on port `8587`, UDP/SPNET discovery on port `6454`
- Layout: two RGB PWM output channels

## Features

- Two Home Assistant RGB light entities, one per output channel
- Local status polling
- Local on/off, RGB color, and brightness control
- UDP discovery for model, MAC, and local name
- IP recovery when the controller keeps the same MAC but receives a new IP
- Device registry MAC connection
- Config entry diagnostics
- Options flow for IP, port, display name, and polling interval

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

Use the controller IP address and port `8587`.

New entries use the discovered MAC address as the stable unique ID when the
controller answers the UDP discovery probe. Existing entries keep their current
unique ID so entity IDs do not unexpectedly change.

Use the integration options in Home Assistant to update:

- IP / host
- Port
- Display name
- Polling interval, from `5` to `300` seconds

## Supported Commands

- Status query
- Per-channel on/off
- Per-channel static RGB color and brightness

The standalone brightness command is intentionally not enabled. The tested
controller did not use a simple `[channel, brightness]` payload for command
`0x51`; brightness is set together with RGB color through command `0x52`.

## Development

Run the protocol tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/banlanx_ft001 -q
```

Run a syntax check:

```bash
python -m compileall custom_components/banlanx_ft001
```

## Credits

The UDP discovery packet format was cross-checked against the public UniLED
scanner implementation. The FT001 TCP status and control behavior was verified
against a real controller.
