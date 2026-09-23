import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "system" / "tailscale-decky-bridge.py"
SPEC = importlib.util.spec_from_file_location("tailscale_decky_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class BridgeCommandTests(unittest.TestCase):
    def test_exit_node_command_uses_argument_list(self):
        command = bridge.network_command("set_exit", {"exit_node": "100.10.0.2", "allow_lan_access": False})
        self.assertEqual(command, [bridge.TAILSCALE, "set", "--exit-node=100.10.0.2", "--exit-node-allow-lan-access=false"])

    def test_empty_exit_node_clears_only_the_exit_node(self):
        self.assertEqual(bridge.network_command("set_exit", {}), [bridge.TAILSCALE, "set", "--exit-node="])

    def test_logout_uses_fixed_command(self):
        self.assertEqual(bridge.network_command("logout", {}), [bridge.TAILSCALE, "logout"])

    def test_custom_flags_are_not_shell_input(self):
        command = bridge.network_command("apply_settings", {"custom_flags": "--accept-routes --shields-up=false"})
        self.assertEqual(command, [bridge.TAILSCALE, "up", "--reset", "--timeout=20s", "--accept-routes", "--shields-up=false"])

    def test_invalid_exit_node_is_rejected(self):
        with self.assertRaises(ValueError):
            bridge.network_command("set_exit", {"exit_node": "100.10.0.2;reboot"})

    def test_up_waiting_for_login_is_a_successful_link_request(self):
        completed = bridge.subprocess.CompletedProcess(
            [bridge.TAILSCALE, "up"],
            1,
            stderr="To authenticate, visit:\n\n\thttps://login.tailscale.com/a/example\n",
        )
        with patch.object(bridge.subprocess, "run", return_value=completed):
            result = bridge.run_command([bridge.TAILSCALE, "up", "--timeout=20s"])
        self.assertTrue(result["ok"])
        self.assertIn("login.tailscale.com", result["detail"])


if __name__ == "__main__":
    unittest.main()
