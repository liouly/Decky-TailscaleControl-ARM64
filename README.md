# Decky-TailscaleControl-ARM64

[中文文档](README.zh-CN.md)

Decky plugin for controlling Tailscale from Steam Game Mode on Armada ARM64 handhelds running Fedora with FEX. It keeps privileged ARM-native work outside Decky's x86 FEX runtime through a narrowly scoped local bridge service.

This is not a drop-in plugin for a stock x86 Steam Deck. It is designed and tested for the Armada layout using the `armada` account and `/var/home/armada/homebrew`.

## Features

- Connect or disconnect the Tailnet with `tailscale up` and `tailscale down`.
- Restart `tailscaled` for recovery without exposing service start/stop buttons.
- Select Tailnet exit nodes and optionally retain LAN access.
- Configure a login server and advanced `tailscale up` flags.
- View Tailscale/LAN IPv4 and IPv6 addresses, peer status, service state, and diagnostics.
- Sign out with confirmation, open the Tailscale login page in Steam's full-screen browser, and close that browser automatically once login succeeds.

## Requirements

- An Armada ARM64 Fedora/FEX handheld using the `armada` account.
- Decky Loader already installed and running.
- Tailscale already installed and working from the command line.
- SSH or a desktop terminal with `sudo` access for the initial bridge-service installation.

## Download

Download `Decky-TailscaleControl-ARM64-<version>.zip` from [GitHub Releases](https://github.com/liouly/Decky-TailscaleControl-ARM64/releases).

## Install Or Upgrade

The ZIP contains both the Decky plugin and native bridge files. A Decky ZIP install alone is not enough: the bridge service must also be installed so that the FEX-hosted plugin can safely invoke ARM-native Tailscale commands.

Copy the release ZIP to the handheld, then run the following commands as the `armada` user. Replace `<version>` with the downloaded release version.

```sh
unzip -q ~/Downloads/Decky-TailscaleControl-ARM64-<version>.zip -d /var/tmp/decky-tailscale
sudo rm -rf /var/home/armada/homebrew/plugins/DeckyTailscaleControl
sudo mv /var/tmp/decky-tailscale/DeckyTailscaleControl /var/home/armada/homebrew/plugins/
sudo install -m 0755 \
  /var/home/armada/homebrew/plugins/DeckyTailscaleControl/system/tailscale-decky-bridge.py \
  /var/home/armada/homebrew/services/tailscale-decky-bridge.py
sudo install -m 0644 \
  /var/home/armada/homebrew/plugins/DeckyTailscaleControl/system/tailscale-decky-bridge.service \
  /etc/systemd/system/tailscale-decky-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now tailscale-decky-bridge.service
sudo systemctl restart plugin_loader.service
rm -rf /var/tmp/decky-tailscale
```

Verify the native bridge:

```sh
systemctl is-active tailscale-decky-bridge.service
```

It should print `active`. Exit and re-enter the Decky plugin page after installation.

## Use

1. Open the Quick Access Menu, then open Decky's `Tailscale` plugin.
2. Use **Tailscale Connection** for normal connect/disconnect operations. Do not use a daemon restart for ordinary disconnects.
3. Select an **Exit Node** when required. The LAN-access switch applies only while an exit node is selected.
4. Use **Advanced Connection Settings** only for a custom login server or explicit `tailscale up` flags. Applying it invokes `tailscale up --reset`, which restores unspecified preferences to their defaults.
5. **Sign out of Tailscale** removes this device from the current Tailnet. After confirmation, select **Go to web login**. Steam opens Tailscale in a full-screen browser and the plugin closes it automatically when authorization succeeds.

## Safety Notes

- `tailscale down` disconnects the overlay network but leaves `tailscaled.service` running.
- Restarting Tailscale is a recovery action and may briefly interrupt Tailscale SSH.
- Signing out requires fresh authorization.
- The native bridge accepts only a fixed allowlist of Tailscale and `tailscaled.service` actions. Custom flags are passed as arguments, never to a shell.

## Build

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node ./node_modules/typescript/bin/tsc --noEmit
node ./node_modules/rollup/dist/bin/rollup -c
python3 scripts/package.py
```

The release archive is written to `out/Decky-TailscaleControl-ARM64-<version>.zip`.

## Upstream Attribution And Licenses

The connection workflow and feature set were informed by [Tailscale Control](https://github.com/saumya-banthia/tailscale-control), copyright 2023 Saumya Banthia, licensed under BSD-3-Clause. This project is independently implemented for the Armada ARM Fedora/FEX environment and does not package the upstream source repository.

The BSD-3-Clause notice is preserved in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSES/tailscale-control-BSD-3-Clause.txt](LICENSES/tailscale-control-BSD-3-Clause.txt), including in release ZIP files. This project itself is licensed under the [MIT License](LICENSE). No upstream author or contributor endorses this project.
