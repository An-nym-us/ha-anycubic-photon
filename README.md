# Anycubic Photon for Home Assistant

A custom Home Assistant integration for the **Anycubic Photon Mono M3 Premium**
and other Anycubic Photon resin printers. It connects one of two ways:

- **Local network (LAN)**: talks to the printer directly on TCP port 6000.
  Fast (15 s updates), no account needed, but it needs the printer's IP.
- **Anycubic Cloud**: goes through your Anycubic account, the same service
  the Anycubic app uses. It keeps working when the printer's IP changes.
  Updates every 60 s and needs internet.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Status | sensor | `printing`, `paused`, `idle`, `finished`, … (cloud also: `offline`, `cancelled`, `downloading`, `preheating`). The `raw_status` attribute has the printer's own reply |
| Progress | sensor | % |
| Current layer / Total layers | sensor | |
| Elapsed time / Time remaining | sensor | duration |
| File | sensor | Name of the file being printed |
| Resin required | sensor | mL, LAN only |
| Layer height | sensor (diagnostic) | mm, LAN only |
| Printing | binary sensor | On while a print is running |
| Pause / Resume / Stop print | button | |

Job sensors show *unknown* when nothing is printing.

## Install

**HACS (custom repository):** in HACS go to ⋮ → *Custom repositories*, add
`https://github.com/An-nym-us/ha-anycubic-photon` as type *Integration*, and
install *Anycubic Photon*.

**Manual:** copy `custom_components/anycubic_photon` into your Home Assistant
`config/custom_components/` folder.

Restart Home Assistant, then go to **Settings → Devices & services → Add
integration → Anycubic Photon** and choose LAN or Anycubic Cloud.

## Setting up Anycubic Cloud

Anycubic has no official sign-in for third-party apps, so you paste a token
instead of a password. Two kinds work:

**Slicer Next token (recommended, lasts about 90 days)**

1. Install Anycubic Slicer Next (free, from Anycubic's website) on Windows
   and sign in with the account your printer is linked to. You don't need
   an FDM printer; it's only used to sign in.
2. Close Slicer Next.
3. Open PowerShell and run this. It copies the token to your clipboard
   without showing it:

   ```powershell
   $m = Get-ChildItem "$env:APPDATA\AnycubicSlicerNext\log\debug_*.log" | Sort-Object LastWriteTime -Descending | Select-String -Pattern 'id_token=(eyJ[\w-]+\.[\w-]+\.[\w-]+)' | Select-Object -First 1; if ($m) { Set-Clipboard $m.Matches[0].Groups[1].Value; "Token copied to clipboard" } else { "No token found. Sign in to Slicer Next, close it, and try again." }
   ```

4. Paste it into the integration and pick **Slicer Next token**.

This is for Slicer Next 2.x, which writes the login token to its debug log.
Older versions stored it instead as `access_token` in
`%AppData%\AnycubicSlicerNext\AnycubicSlicerNext.conf`; that value works
too.

The token is valid for about 90 days. Home Assistant asks for a new one
when it expires: sign in to Slicer Next again and repeat step 3.

**Web token (quicker, but expires)**

1. Sign in at <https://cloud-universe.anycubic.com/file>.
2. Press F12, open the **Console** tab and run
   `window.localStorage["XX-Token"]`.
3. Copy the value, without quotes, and pick **Web token**.

When a token stops working, Home Assistant shows a **Re-authenticate**
notice. Paste a new token there; nothing else needs setting up again.

Treat either token like a password: anyone who has it can control your
printers.

## Setting up LAN

Check that your printer speaks the LAN protocol by running the built-in probe
from any computer on the same network (Python 3.10+, no extra packages):

```
python custom_components/anycubic_photon/api.py 192.168.1.50
```

If you see a `sysinfo:` line with your model and serial number, LAN mode
works. Give the printer a fixed IP (a DHCP reservation in your router) so it
doesn't move.

## Options

The update interval (default 15 s for LAN, 60 s for cloud) can be changed
under the integration's **Configure** button. Cloud mode won't go below
30 s, to avoid hammering Anycubic's servers.

## Known limitations

- Neither the LAN protocol nor the cloud API is documented by Anycubic. Both
  come from community reverse engineering, and Anycubic can change the cloud
  API at any time. The cloud mode is based on the endpoints used by
  [hass-anycubic_cloud](https://github.com/WaresWichall/hass-anycubic_cloud).
- Cloud mode has been checked against a real Photon M3 Premium for sign-in
  and printer status. Progress, layers and times come from Anycubic's
  record of the print job. Prints started at the printer (for example from
  USB) may have no such record; the printer then shows as `printing`
  without details.
- If a sensor shows a wrong value, check the `raw_status` attribute on the
  Status sensor and open an issue.
- Starting a print and listing files on the printer aren't supported yet.
