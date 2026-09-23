import ipaddress
import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


SERVICE_NAME = "tailscaled.service"
TAILSCALE_INTERFACE = "tailscale0"
CONTROL_SOCKET = "/run/tailscale-decky-control.sock"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str], float], CommandResult]
ActionRunner = Callable[[str], None]


def system_runner(command: Sequence[str], timeout: float) -> CommandResult:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class TailscaleController:
    """Read and control the system-wide Tailscale service used by Decky."""

    def __init__(
        self,
        runner: Runner = system_runner,
        command_available: Optional[Callable[[str], bool]] = None,
        sleeper: Callable[[float], None] = time.sleep,
        action_runner: Optional[ActionRunner] = None,
    ):
        self._runner = runner
        self._command_available = command_available or (lambda name: shutil.which(name) is not None)
        self._sleeper = sleeper
        self._action_runner = action_runner or self._run_service_action

    def _run(self, command: Sequence[str], timeout: float = 8) -> CommandResult:
        try:
            return self._runner(command, timeout)
        except subprocess.TimeoutExpired:
            return CommandResult(124, stderr=f"Command timed out: {' '.join(command)}")
        except OSError as error:
            return CommandResult(127, stderr=str(error))

    @staticmethod
    def _bridge_request(payload: dict) -> dict:
        """Send a structured request to the native bridge from Decky's FEX runtime."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(25)
                client.connect(CONTROL_SOCKET)
                client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                response = b""
                while b"\n" not in response:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    response += chunk
        except OSError as error:
            raise RuntimeError(f"Tailscale 控制服务不可用：{error}") from error

        try:
            result = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Tailscale 控制服务返回了无效响应") from error
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "Tailscale 控制服务拒绝了请求"))
        return result

    @classmethod
    def _run_service_action(cls, action: str) -> None:
        cls._bridge_request({"action": action})

    @staticmethod
    def _message(result: CommandResult) -> str:
        return (result.stderr or result.stdout).strip()

    def _service_state(self) -> dict:
        systemctl_available = self._command_available("systemctl")
        if not systemctl_available:
            return {"installed": False, "active": False, "enabled": "unknown", "message": "systemctl is unavailable"}

        active = self._run(["systemctl", "is-active", "--quiet", SERVICE_NAME])
        enabled = self._run(["systemctl", "is-enabled", SERVICE_NAME])
        enabled_value = enabled.stdout.strip() if enabled.returncode == 0 else "disabled"
        message = "" if active.returncode == 0 else self._message(active)
        return {
            "installed": True,
            "active": active.returncode == 0,
            "enabled": enabled_value,
            "message": message,
        }

    def _tailscale_status(self) -> tuple[dict, str]:
        if not self._command_available("tailscale"):
            return {}, "tailscale command is unavailable"
        result = self._run(["tailscale", "status", "--json"])
        if result.returncode != 0:
            return {}, self._message(result) or "tailscale status failed"
        try:
            return json.loads(result.stdout), ""
        except json.JSONDecodeError as error:
            return {}, f"tailscale returned invalid JSON: {error.msg}"

    def _network_addresses(self) -> tuple[list[dict], str]:
        if not self._command_available("ip"):
            return [], "ip command is unavailable"
        result = self._run(["ip", "-j", "address", "show"])
        if result.returncode != 0:
            return [], self._message(result) or "could not inspect network interfaces"
        try:
            interfaces = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            return [], f"ip returned invalid JSON: {error.msg}"

        addresses = []
        for interface in interfaces:
            name = interface.get("ifname", "unknown")
            if name in {"lo", TAILSCALE_INTERFACE}:
                continue
            ipv4, ipv6 = [], []
            for entry in interface.get("addr_info", []):
                if entry.get("scope") != "global":
                    continue
                local = entry.get("local")
                family = entry.get("family")
                if not local:
                    continue
                try:
                    address = ipaddress.ip_address(local)
                except ValueError:
                    continue
                if address.is_loopback or address.is_link_local:
                    continue
                (ipv4 if family == "inet" else ipv6).append(str(address))
            if ipv4 or ipv6:
                addresses.append({"interface": name, "ipv4": ipv4, "ipv6": ipv6})
        return addresses, ""

    @staticmethod
    def _split_ips(values: Sequence[str]) -> tuple[list[str], list[str]]:
        ipv4, ipv6 = [], []
        for value in values:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            (ipv4 if address.version == 4 else ipv6).append(str(address))
        return ipv4, ipv6

    def _peer_details(self, status: dict) -> tuple[list[dict], list[dict], str]:
        raw_peers = status.get("Peer", {})
        peers = raw_peers.values() if isinstance(raw_peers, dict) else []
        all_peers, exit_nodes, selected_exit_node = [], [], ""
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            ipv4, _ = self._split_ips(peer.get("TailscaleIPs", []))
            item = {
                "hostname": str(peer.get("HostName") or peer.get("DNSName") or "未知设备"),
                "ipv4": ipv4[0] if ipv4 else "",
                "online": bool(peer.get("Online", False)),
                "active": bool(peer.get("Active", False)),
            }
            all_peers.append(item)
            if bool(peer.get("ExitNodeOption", False)) and item["ipv4"]:
                exit_nodes.append(item)
            if bool(peer.get("ExitNode", False)) and item["ipv4"]:
                selected_exit_node = item["ipv4"]
        return all_peers, exit_nodes, selected_exit_node

    @staticmethod
    def _health_messages(values: object) -> tuple[list[str], bool]:
        """Keep optional connmark warnings concise without hiding other health errors."""
        if not isinstance(values, list):
            return [], False
        raw_messages = [" ".join(value.split()) for value in values if isinstance(value, str)]
        connmark_unavailable = any(
            "connmark" in value and "operation not supported" in value for value in raw_messages
        )
        messages, seen = [], set()
        for normalized in raw_messages:
            if "connmark" in normalized and "operation not supported" in normalized:
                continue
            if connmark_unavailable and "netlink receive: operation not supported" in normalized:
                continue
            if normalized and normalized not in seen:
                messages.append(normalized)
                seen.add(normalized)
        return messages, connmark_unavailable

    def snapshot(self) -> dict:
        service = self._service_state()
        status, status_error = self._tailscale_status()
        self_status = status.get("Self", {}) if isinstance(status.get("Self", {}), dict) else {}
        ips = status.get("TailscaleIPs") or self_status.get("TailscaleIPs") or []
        ipv4, ipv6 = self._split_ips(ips if isinstance(ips, list) else [])
        interfaces, network_error = self._network_addresses()

        backend_state = str(status.get("BackendState", ""))
        online = bool(self_status.get("Online", False))
        peers, exit_nodes, selected_exit_node = self._peer_details(status)
        if not service["active"]:
            connection = "stopped"
        elif status_error:
            connection = "unknown"
        elif backend_state == "Running" and online:
            connection = "connected"
        elif backend_state in {"Stopped", "NeedsLogin"}:
            connection = "disconnected"
        else:
            connection = "connecting"

        health, connmark_unavailable = self._health_messages(status.get("Health", []))
        return {
            "service": service,
            "connection": {
                "state": connection,
                "backend_state": backend_state or "unknown",
                "online": online,
                "health": health,
                "connmark_unavailable": connmark_unavailable,
                "message": status_error,
            },
            "tailscale": {
                "ipv4": ipv4,
                "ipv6": ipv6,
                "version": str(status.get("Version", "")),
                "auth_url": str(status.get("AuthURL", "")),
                "peers": peers,
                "exit_nodes": exit_nodes,
                "selected_exit_node": selected_exit_node,
            },
            "network": {"interfaces": interfaces, "message": network_error},
        }

    def service_action(self, action: str) -> dict:
        if action not in {"start", "stop", "restart"}:
            raise ValueError("Unsupported service action")
        self._action_runner(action)
        self._sleeper(0.75 if action != "stop" else 0.25)
        return self.snapshot()

    def network_action(self, action: str, settings: Optional[dict] = None) -> dict:
        if action not in {"up", "down", "set_exit", "apply_settings", "logout"}:
            raise ValueError("Unsupported network action")
        payload = {"action": action, "settings": settings or {}}
        self._bridge_request(payload)
        if action == "logout":
            # Request a fresh AuthURL for the Decky login view.
            up_error = None
            try:
                self._bridge_request({"action": "up", "settings": {}})
            except RuntimeError as error:
                up_error = error

            # On this Tailscale build, `up` can time out while waiting for a
            # browser login even after it has successfully entered NeedsLogin.
            for _ in range(8):
                status = self.snapshot()
                if status["connection"]["backend_state"] == "NeedsLogin":
                    return status
                self._sleeper(1.0)
            if up_error:
                raise up_error
        self._sleeper(1.0 if action != "down" else 0.25)
        return self.snapshot()
