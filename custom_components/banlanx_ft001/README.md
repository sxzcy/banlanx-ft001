# BanlanX FT001

Home Assistant custom integration for the BanlanX FT001 fish tank light controller.

This is a local WiFi integration. It talks to the controller directly over TCP
port 8587 using the verified `SPTECH` protocol. BLE is not required.

## Verified Device

- Model: `FT001`
- Model code: `150` / `0x96`
- Layout: two RGB PWM output channels
- Tested controller: `192.168.1.204:8587`
- Tested WiFi MAC: `B4:14:CD:71:19:DF`
- Tested local name: `FT00119DF`
- Tested firmware: `V1.0.08`

## Supported Now

- Poll status over WiFi
- Discover the controller over local UDP/SPNET and record MAC/model metadata
- Recover automatically when the controller keeps the same MAC but receives a new IP address
- Create two Home Assistant light entities
- Per-channel on/off
- Per-channel RGB color and brightness via the static color command
- Home Assistant diagnostics for the config entry
- Options flow for updating IP, port, display name, and polling interval

## Install

Copy this folder to Home Assistant:

```text
custom_components/banlanx_ft001
```

Restart Home Assistant, then add the integration from the UI:

```text
Settings -> Devices & services -> Add integration -> BanlanX FT001
```

Use the controller IP address and port `8587`.

New config entries use the discovered MAC address as the stable unique ID when
the controller answers the UDP discovery probe. Existing entries keep their
current unique ID so Home Assistant entity IDs do not unexpectedly change.

When an entry has a MAC address and the configured IP stops responding, the
coordinator broadcasts the UDP discovery probe, updates the stored host when it
finds the same MAC, and retries the status read once.

Use the integration options in Home Assistant to update the controller IP,
port, display name, or polling interval without deleting and re-adding the
device.

## Notes

The standalone brightness command is not enabled because the tested controller
does not use a simple `[channel, brightness]` payload for command `0x51`.
Brightness is currently set together with RGB color through command `0x52`.
