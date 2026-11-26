# Anycubic Photon (LAN) for Home Assistant

A custom Home Assistant integration for the **Anycubic Photon Mono M3 Premium**
(and other Photon printers that use Anycubic's local LAN protocol on TCP port
6000, such as the Mono X, Mono X 6K and Mono SE). It talks to the printer
directly on your network. No Anycubic cloud account is needed.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Status | sensor | Raw printer state (`print`, `pause`, `stop`, …). The full reply is in the `raw_status` attribute |
| Progress | sensor | % |
| Current layer / Total layers | sensor | |
| Elapsed time / Time remaining | sensor | duration |
| File | sensor | Name of the file being printed |
| Resin required | sensor | mL, as reported by the slicer |
| Layer height | sensor (diagnostic) | mm |
| Printing | binary sensor | On while a print is running |
| Pause / Resume / Stop print | button | |

Job sensors show *unknown* when nothing is printing.

## 1. Check that your printer speaks the LAN protocol

Before installing, run the built-in probe from any computer on the same
network (needs Python 3.10+, no extra packages):

```
python custom_components/anycubic_photon/api.py 192.168.1.50
```

Replace the IP with your printer's (shown on the printer under network
settings). If you see a `sysinfo:` line with your model and serial number,
the integration will work. If it fails with "Cannot connect", your
firmware doesn't expose port 6000; see **If the probe fails** below.

## 2. Install

**HACS (custom repository):** in HACS go to ⋮ → *Custom repositories*, add
`https://github.com/An-nym-us/ha-anycubic-photon` as type *Integration*, and
install *Anycubic Photon (LAN)*.

**Manual:** copy `custom_components/anycubic_photon` into your Home Assistant
`config/custom_components/` folder.

Restart Home Assistant, then go to **Settings → Devices & services → Add
integration → Anycubic Photon (LAN)** and enter the printer's IP address.

Give the printer a fixed IP (a DHCP reservation in your router) so it
doesn't move.

## Options

The update interval defaults to 15 seconds. Change it under the
integration's **Configure** button.

## If the probe fails

Some newer Anycubic firmware only talks to Anycubic Cloud and doesn't open
port 6000. In that case, try updating the printer firmware, or use the
cloud-based [hass-anycubic_cloud](https://github.com/WaresWichall/hass-anycubic_cloud)
integration instead.

## Known limitations

- The protocol is undocumented. Field meanings come from community reverse
  engineering of the Mono X. If a sensor shows a wrong value on your M3
  Premium, check the `raw_status` attribute on the Status sensor and adjust
  `parse_status()` in `api.py`.
- Starting a print and listing files on the printer aren't exposed yet.
