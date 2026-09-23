# Tailscale Control

Decky plugin for Armada ARM handhelds. It controls Tailscale from Steam Game Mode and includes a recovery restart control for the system service.

## Features

- Connect or disconnect the Tailscale network with `tailscale up` and `tailscale down`.
- Select a Tailscale exit node and keep LAN access while it is active.
- Apply a custom login server and `tailscale up` flags.
- Sign out of the current Tailscale account after an explicit confirmation.
- Open the current Tailscale authorization URL in Steam's full-screen browser, then close that browser automatically after successful login.
- Display Tailnet device status, exit nodes, Tailscale IPv4/IPv6, local network addresses, and service diagnostics.
- Restart `tailscaled.service` when recovery is needed, and refresh the displayed state.

## Armada ARM Design

Decky runs the plugin backend in an x86 FEX runtime, while the system Tailscale tools are ARM-native. The companion `tailscale-decky-bridge.service` runs natively and accepts only fixed Tailscale and `tailscaled.service` actions over a Unix socket accessible only to the `armada` account. It does not execute shell input from the plugin.

## Safety

- `tailscale down` disconnects the overlay network but leaves `tailscaled.service` running.
- The plugin intentionally does not expose service start or stop controls. Normal connection management uses `tailscale up` and `tailscale down`.
- Signing out runs `tailscale logout`, then requests a new login URL. The plugin switches to its login view until authorization completes.
- Applying advanced settings uses `tailscale up --reset`; unspecified Tailscale preferences return to their defaults.
- Custom flags are passed as command arguments, never to a shell.

## Upstream Reference

The connection controls are informed by `saumya-banthia/tailscale-control` (BSD-3-Clause). This project does not package upstream source code and replaces its SteamOS-specific backend with an Armada ARM native bridge.

## Build

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node ./node_modules/typescript/bin/tsc --noEmit
node ./node_modules/rollup/dist/bin/rollup -c
python3 scripts/package.py
```

The archive is written to `out/DeckyTailscaleControl-<version>.zip`.
