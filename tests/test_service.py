import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py_modules"))

from tailscale_control.service import CommandResult, TailscaleController


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.status_responses = []

    def __call__(self, command, timeout):
        self.commands.append(tuple(command))
        if command[:3] == ["systemctl", "is-active", "--quiet"]:
            return CommandResult(0)
        if command[:2] == ["systemctl", "is-enabled"]:
            return CommandResult(0, "enabled\n")
        if command == ["tailscale", "status", "--json"]:
            status = self.status_responses.pop(0) if self.status_responses else {
                "BackendState": "Running",
                "TailscaleIPs": ["100.70.180.93", "fd7a:115c:a1e0::42"],
                "Self": {"Online": True},
            }
            return CommandResult(0, json.dumps(status))
        if command == ["ip", "-j", "address", "show"]:
            return CommandResult(0, json.dumps([
                {"ifname": "lo", "addr_info": []},
                {"ifname": "tailscale0", "addr_info": [{"family": "inet", "scope": "global", "local": "100.70.180.93"}]},
                {"ifname": "wlan0", "addr_info": [
                    {"family": "inet", "scope": "global", "local": "192.168.1.20"},
                    {"family": "inet6", "scope": "global", "local": "2408:8207:1::20"},
                ]},
            ]))
        raise AssertionError(command)


class TailscaleControllerTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.actions = []
        self.controller = TailscaleController(self.runner, lambda _: True, lambda _: None, self.actions.append)

    def test_snapshot_splits_tailscale_and_lan_addresses(self):
        status = self.controller.snapshot()
        self.assertTrue(status["service"]["active"])
        self.assertEqual(status["connection"]["state"], "connected")
        self.assertEqual(status["tailscale"]["ipv4"], ["100.70.180.93"])
        self.assertEqual(status["tailscale"]["ipv6"], ["fd7a:115c:a1e0::42"])
        self.assertEqual(status["network"]["interfaces"], [{
            "interface": "wlan0", "ipv4": ["192.168.1.20"], "ipv6": ["2408:8207:1::20"],
        }])

    def test_restart_uses_fixed_service_name(self):
        status = self.controller.service_action("restart")
        self.assertTrue(status["service"]["active"])
        self.assertEqual(self.actions, ["restart"])

    def test_logout_requests_a_new_login_url(self):
        with patch.object(TailscaleController, "_bridge_request") as bridge_request:
            self.controller.network_action("logout")
        self.assertEqual(
            bridge_request.call_args_list,
            [
                (({"action": "logout", "settings": {}},),),
                (({"action": "up", "settings": {}},),),
            ],
        )

    def test_logout_waits_for_needs_login_after_up_times_out(self):
        self.runner.status_responses = [
            {"BackendState": "Running", "Self": {"Online": True}},
            {"BackendState": "NeedsLogin", "AuthURL": "https://login.tailscale.com/a/example", "Self": {"Online": False}},
        ]
        with patch.object(
            TailscaleController,
            "_bridge_request",
            side_effect=[{}, RuntimeError("waiting for login")],
        ):
            status = self.controller.network_action("logout")
        self.assertEqual(status["connection"]["backend_state"], "NeedsLogin")
        self.assertEqual(status["tailscale"]["auth_url"], "https://login.tailscale.com/a/example")

    def test_connmark_warning_is_summarized(self):
        messages, unavailable = self.controller._health_messages([
            "enabling connmark rules: netlink receive: operation not supported",
            "netlink receive: operation not supported",
            "login server is unreachable",
        ])
        self.assertTrue(unavailable)
        self.assertEqual(messages, ["login server is unreachable"])

    def test_peer_details_extracts_exit_nodes(self):
        peers, exit_nodes, selected = self.controller._peer_details({"Peer": {
            "one": {"HostName": "laptop", "TailscaleIPs": ["100.10.0.2"], "Online": True, "ExitNodeOption": True},
            "two": {"HostName": "server", "TailscaleIPs": ["100.10.0.3"], "Online": False, "ExitNode": True},
        }})
        self.assertEqual(peers[0]["hostname"], "laptop")
        self.assertEqual(exit_nodes, [{"hostname": "laptop", "ipv4": "100.10.0.2", "online": True, "active": False}])
        self.assertEqual(selected, "100.10.0.3")

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            self.controller.service_action("enable")


if __name__ == "__main__":
    unittest.main()
