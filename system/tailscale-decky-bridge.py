#!/usr/bin/python3
"""Native, tightly scoped bridge for Decky's x86 FEX plugin runtime."""
import json
import os
import pwd
import shlex
import socket
import subprocess
import ipaddress


SOCKET_PATH = "/run/tailscale-decky-control.sock"
SERVICE_NAME = "tailscaled.service"
SYSTEMCTL = "/usr/bin/systemctl"
TAILSCALE = "/usr/bin/tailscale"
SERVICE_ACTIONS = {"start", "stop", "restart"}
NETWORK_ACTIONS = {"up", "down", "reauth", "set_exit", "apply_settings", "logout"}


def send_response(client, payload):
    client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))


def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip() or "命令执行失败"
        if command[:2] == [TAILSCALE, "up"] and "To authenticate, visit:" in detail:
            return {"ok": True, "detail": detail}
        return {"ok": False, "error": detail}
    return {"ok": True, "detail": (result.stdout or result.stderr).strip()}


def exit_node(value):
    value = str(value or "")
    if not value:
        return ""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise ValueError("出口节点必须是 IPv4 或 IPv6 地址") from error


def network_command(action, settings):
    settings = settings if isinstance(settings, dict) else {}
    if action == "down":
        return [TAILSCALE, "down"]
    if action == "up":
        return [TAILSCALE, "up", "--timeout=20s"]
    if action == "reauth":
        return [TAILSCALE, "up", "--force-reauth", "--timeout=20s"]
    if action == "logout":
        return [TAILSCALE, "logout"]
    if action == "set_exit":
        selected = exit_node(settings.get("exit_node"))
        command = [TAILSCALE, "set", f"--exit-node={selected}"]
        if selected:
            command.append(f"--exit-node-allow-lan-access={'true' if settings.get('allow_lan_access', True) else 'false'}")
        return command
    if action == "apply_settings":
        login_server = str(settings.get("login_server") or "").strip()
        if login_server and not login_server.startswith(("https://", "http://")):
            raise ValueError("登录服务器必须以 http:// 或 https:// 开头")
        custom_flags = str(settings.get("custom_flags") or "").strip()
        flags = shlex.split(custom_flags) if custom_flags else []
        if any(not flag.startswith("-") for flag in flags):
            raise ValueError("自定义参数必须以 - 或 -- 开头")
        command = [TAILSCALE, "up", "--reset", "--timeout=20s"]
        if login_server:
            command.append(f"--login-server={login_server}")
        command.extend(flags)
        return command
    raise ValueError("不允许的网络操作")


def handle(client):
    client.settimeout(30)
    request = b""
    while b"\n" not in request and len(request) < 4096:
        chunk = client.recv(4096)
        if not chunk:
            break
        request += chunk
    try:
        payload = json.loads(request.decode("utf-8"))
        action = payload.get("action") if isinstance(payload, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        send_response(client, {"ok": False, "error": "请求格式无效"})
        return
    if action not in SERVICE_ACTIONS | NETWORK_ACTIONS:
        send_response(client, {"ok": False, "error": "不允许的服务操作"})
        return
    try:
        command = [SYSTEMCTL, action, SERVICE_NAME] if action in SERVICE_ACTIONS else network_command(action, payload.get("settings"))
    except ValueError as error:
        send_response(client, {"ok": False, "error": str(error)})
        return
    send_response(client, run_command(command))


def main():
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    armada = pwd.getpwnam("armada")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(SOCKET_PATH)
        os.chown(SOCKET_PATH, armada.pw_uid, armada.pw_gid)
        os.chmod(SOCKET_PATH, 0o600)
        server.listen(8)
        while True:
            client, _ = server.accept()
            with client:
                try:
                    handle(client)
                except (OSError, subprocess.SubprocessError) as error:
                    send_response(client, {"ok": False, "error": f"控制服务错误：{error}"})


if __name__ == "__main__":
    main()
