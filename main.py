import asyncio

import decky

from tailscale_control.service import TailscaleController


class Plugin:
    def __init__(self):
        self.controller = TailscaleController()
        self.running = False

    async def get_status(self):
        return await asyncio.to_thread(self.controller.snapshot)

    async def service_action(self, action):
        decky.logger.info("tailscale-control action requested: %s", action)
        try:
            status = await asyncio.to_thread(self.controller.service_action, action)
            decky.logger.info(
                "tailscale-control action succeeded: %s (active=%s, connection=%s)",
                action,
                status["service"]["active"],
                status["connection"]["state"],
            )
            return {"ok": True, "status": status}
        except Exception as error:
            # Decky's RPC layer turns Python exceptions into an unhelpful generic message.
            decky.logger.error("tailscale-control action failed: %s (%s)", action, error)
            status = await asyncio.to_thread(self.controller.snapshot)
            return {"ok": False, "status": status, "message": str(error) or "服务操作失败"}

    async def network_action(self, action, settings=None):
        decky.logger.info("tailscale-control network action requested: %s", action)
        try:
            status = await asyncio.to_thread(self.controller.network_action, action, settings)
            decky.logger.info(
                "tailscale-control network action succeeded: %s (connection=%s)",
                action,
                status["connection"]["state"],
            )
            return {"ok": True, "status": status}
        except Exception as error:
            decky.logger.error("tailscale-control network action failed: %s (%s)", action, error)
            status = await asyncio.to_thread(self.controller.snapshot)
            return {"ok": False, "status": status, "message": str(error) or "网络操作失败"}

    async def _main(self):
        self.running = True
        while self.running:
            await asyncio.sleep(1)

    async def _unload(self):
        self.running = False
