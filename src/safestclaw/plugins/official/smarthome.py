"""
SafestClaw Smart Home Plugin - Control lights and devices.

Supports:
- Philips Hue (requires phue: pip install safestclaw[smarthome])
- MQTT (for Home Assistant, etc.)

Config in ~/.safestclaw/config.yaml:
    plugins:
      smarthome:
        hue_bridge: "192.168.1.100"  # Your Hue bridge IP
        mqtt_broker: "localhost"     # MQTT broker for Home Assistant
        mqtt_port: 1883
"""

import logging
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class SmartHomePlugin(BasePlugin):
    """Smart home control plugin for lights and devices."""

    info = PluginInfo(
        name="smarthome",
        version="1.0.0",
        description="Control smart home lights and devices",
        author="SafestClaw",
        keywords=["light", "lights", "lamp", "turn on", "turn off", "dim", "bright", "hue"],
        patterns=[
            r"turn\s+(on|off)\s+(?:the\s+)?(.+?)(?:\s+lights?)?$",
            r"(?:set|dim)\s+(?:the\s+)?(.+?)\s+(?:lights?\s+)?(?:to\s+)?(\d+)%?",
            r"(?:make\s+)?(?:the\s+)?(.+?)\s+(brighter|dimmer)",
        ],
        examples=[
            "turn on living room lights",
            "turn off bedroom",
            "dim kitchen to 50%",
            "make office brighter",
        ],
    )

    def __init__(self):
        self.hue_bridge = None
        self.mqtt_client = None
        self._config: dict = {}

    def on_load(self, engine: Any) -> None:
        """Initialize smart home connections."""
        self._config = engine.config.get("plugins", {}).get("smarthome", {})

        # Try to connect to Hue bridge
        hue_ip = self._config.get("hue_bridge")
        if hue_ip:
            self._init_hue(hue_ip)

        # Try to connect to MQTT
        mqtt_broker = self._config.get("mqtt_broker")
        if mqtt_broker:
            self._init_mqtt(mqtt_broker, self._config.get("mqtt_port", 1883))

    def _init_hue(self, bridge_ip: str) -> None:
        """Initialize Philips Hue connection."""
        try:
            from phue import Bridge
            self.hue_bridge = Bridge(bridge_ip)
            # First time requires pressing the button on the bridge
            self.hue_bridge.connect()
            logger.info(f"Connected to Hue bridge at {bridge_ip}")
        except ImportError:
            logger.warning(
                "phue not installed. Run: pip install safestclaw[smarthome]"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Hue bridge: {e}")

    def _init_mqtt(self, broker: str, port: int) -> None:
        """Initialize MQTT connection for Home Assistant."""
        try:
            import paho.mqtt.client as mqtt
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.connect(broker, port, 60)
            self.mqtt_client.loop_start()
            logger.info(f"Connected to MQTT broker at {broker}:{port}")
        except ImportError:
            logger.warning(
                "paho-mqtt not installed. Run: pip install safestclaw[smarthome]"
            )
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")

    def on_unload(self) -> None:
        """Cleanup connections."""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Execute smart home command."""
        raw_text = params.get("_raw_text", "").lower()

        # Parse action and target from raw text or params
        action = None
        target = None
        level = None

        # Check for on/off
        if "turn on" in raw_text or "switch on" in raw_text:
            action = "on"
        elif "turn off" in raw_text or "switch off" in raw_text:
            action = "off"
        elif "dim" in raw_text or "brighter" in raw_text or "dimmer" in raw_text:
            action = "dim"

        # Extract target room/light
        for word in ["living room", "bedroom", "kitchen", "office", "bathroom", "hallway"]:
            if word in raw_text:
                target = word
                break

        # Extract percentage
        import re
        level_match = re.search(r'(\d+)\s*%?', raw_text)
        if level_match:
            level = int(level_match.group(1))

        if "brighter" in raw_text:
            level = min(100, (level or 50) + 25)
        elif "dimmer" in raw_text:
            level = max(0, (level or 50) - 25)

        # No smart home backend configured
        if not self.hue_bridge and not self.mqtt_client:
            return self._simulate_action(action, target, level)

        # Execute via Hue
        if self.hue_bridge and action:
            return self._execute_hue(action, target, level)

        # Execute via MQTT (Home Assistant)
        if self.mqtt_client and action:
            return self._execute_mqtt(action, target, level)

        return "Could not understand smart home command. Try 'turn on living room lights'"

    def _simulate_action(
        self, action: str | None, target: str | None, level: int | None
    ) -> str:
        """Simulate action when no backend is configured."""
        if not action:
            return (
                "Smart home not configured. Add to config:\n"
                "plugins:\n"
                "  smarthome:\n"
                "    hue_bridge: '192.168.1.100'  # or\n"
                "    mqtt_broker: 'localhost'"
            )

        target = target or "lights"
        if action == "on":
            return f"[Simulated] Turned ON {target}"
        elif action == "off":
            return f"[Simulated] Turned OFF {target}"
        elif action == "dim" and level is not None:
            return f"[Simulated] Set {target} to {level}%"

        return f"[Simulated] {action} {target}"

    def _execute_hue(
        self, action: str, target: str | None, level: int | None
    ) -> str:
        """Execute command via Philips Hue."""
        try:
            lights = self.hue_bridge.lights

            # Find matching lights
            target_lights = []
            for light in lights:
                if target is None or target.lower() in light.name.lower():
                    target_lights.append(light)

            if not target_lights:
                return f"No lights found matching '{target}'"

            for light in target_lights:
                if action == "on":
                    light.on = True
                elif action == "off":
                    light.on = False
                elif action == "dim" and level is not None:
                    light.on = True
                    light.brightness = int(level * 2.54)  # 0-254 scale

            names = ", ".join(light.name for light in target_lights)
            if action == "on":
                return f"Turned ON: {names}"
            elif action == "off":
                return f"Turned OFF: {names}"
            else:
                return f"Set {names} to {level}%"

        except Exception as e:
            logger.error(f"Hue error: {e}")
            return f"Hue error: {e}"

    def _execute_mqtt(
        self, action: str, target: str | None, level: int | None
    ) -> str:
        """Execute command via MQTT (Home Assistant)."""
        try:
            # Home Assistant MQTT convention
            domain = "light"
            payload = {}
            if level is not None and action == "dim":
                payload["brightness_pct"] = level

            # Publish to Home Assistant
            topic = f"homeassistant/{domain}/{target or 'all'}/set"
            import json
            self.mqtt_client.publish(topic, json.dumps({
                "state": "ON" if action != "off" else "OFF",
                **payload,
            }))

            if action == "on":
                return f"Sent ON command to {target or 'all lights'}"
            elif action == "off":
                return f"Sent OFF command to {target or 'all lights'}"
            else:
                return f"Sent dim to {level}% command to {target or 'all lights'}"

        except Exception as e:
            logger.error(f"MQTT error: {e}")
            return f"MQTT error: {e}"
