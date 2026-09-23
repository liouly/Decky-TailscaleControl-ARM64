# Decky-TailscaleControl-ARM64

[English documentation](README.md)

这是一个用于 Armada ARM64 掌机的 Decky 插件，可在 Steam 大屏模式中管理 Tailscale。设备运行 Fedora 与 FEX 时，Decky 后端处于 x86 FEX 运行环境；本项目通过受限的本地原生桥接服务执行 ARM 原生的 Tailscale 命令。

本项目不是面向标准 x86 Steam Deck 的通用插件，已按 `armada` 用户及 `/var/home/armada/homebrew` 目录布局设计和测试。

## 功能

- 使用 `tailscale up` 与 `tailscale down` 连接或断开 Tailnet。
- 在故障恢复时重启 `tailscaled`，不提供服务启动或停止按钮。
- 选择出口节点，并可在使用出口节点时保留局域网访问。
- 设置登录服务器及高级 `tailscale up` 参数。
- 显示 Tailscale/局域网 IPv4、IPv6、节点状态、服务状态和诊断信息。
- 二次确认后退出登录；在 Steam 全屏浏览器中打开 Tailscale 网页登录，并在授权成功后自动关闭该浏览器。

## 前置条件

- 使用 `armada` 用户的 Armada ARM64 Fedora/FEX 掌机。
- 已安装并运行 Decky Loader。
- 已安装 Tailscale，且可在终端中正常工作。
- 首次安装原生桥接服务时，需要 SSH 或桌面终端的 `sudo` 权限。

## 下载

从 [GitHub Releases](https://github.com/liouly/Decky-TailscaleControl-ARM64/releases) 下载 `Decky-TailscaleControl-ARM64-<版本号>.zip`。

## 安装或升级

ZIP 同时包含 Decky 插件与原生桥接文件。仅在 Decky 中安装 ZIP 不足以完成安装，还需要安装桥接服务，使 FEX 中的插件能安全调用 ARM 原生的 Tailscale 命令。

将发布 ZIP 复制到掌机后，以 `armada` 用户执行以下命令。请把 `<版本号>` 替换成下载的实际版本。

```sh
unzip -q ~/Downloads/Decky-TailscaleControl-ARM64-<版本号>.zip -d /var/tmp/decky-tailscale
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

用下面命令确认原生桥接服务已运行：

```sh
systemctl is-active tailscale-decky-bridge.service
```

输出应为 `active`。安装后请退出并重新进入 Decky 插件页面。

## 使用

1. 打开 Steam 快速访问菜单，进入 Decky 的 `Tailscale` 插件。
2. 日常连接或断开请使用 **Tailscale Connection**，不要用重启服务代替断开连接。
3. 需要时选择 **Exit Node**。局域网访问开关仅在已选择出口节点时生效。
4. **Advanced Connection Settings** 仅用于自定义登录服务器或明确的 `tailscale up` 参数。应用设置会执行 `tailscale up --reset`，未指定的偏好会恢复默认值。
5. **Sign out of Tailscale** 会将本设备退出当前 Tailnet。确认退出后，选择 **Go to web login**；Steam 会打开 Tailscale 全屏网页登录，授权成功后插件会自动关闭该页面。
6. 如果登录地址已失效，或网页显示登录成功但插件仍停留在登录页，请选择 **重新获取登录地址**。它会废弃旧链接、请求新的授权地址，并每秒检查一次连接状态。

## 注意事项

- `tailscale down` 只断开覆盖网络，`tailscaled.service` 仍保持运行。
- 重启 Tailscale 用于恢复，可能会短暂中断 Tailscale SSH 连接。
- 退出登录后需要重新授权。
- 原生桥接只接受固定白名单中的 Tailscale 与 `tailscaled.service` 操作；自定义参数以命令参数传递，不会交给 shell 执行。

## 构建

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node ./node_modules/typescript/bin/tsc --noEmit
node ./node_modules/rollup/dist/bin/rollup -c
python3 scripts/package.py
```

发布包会生成到 `out/Decky-TailscaleControl-ARM64-<版本号>.zip`。

## 上游致谢与许可证

连接流程和功能设计参考了 [Tailscale Control](https://github.com/saumya-banthia/tailscale-control)，Copyright 2023 Saumya Banthia，采用 BSD-3-Clause 许可证。本项目为 Armada ARM Fedora/FEX 环境独立实现，不打包上游仓库的源码。

发布包会保留 BSD-3-Clause 许可证与署名，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [LICENSES/tailscale-control-BSD-3-Clause.txt](LICENSES/tailscale-control-BSD-3-Clause.txt)。本项目自身采用 [MIT License](LICENSE)。上游作者及贡献者不为本项目背书。
