"""
SafestClaw Device Discovery Plugin - Scan and control smart devices.

Like OpenClaw/Clawdebot - scans your home for devices via:
- Bluetooth LE (smart bulbs, sensors, locks, etc.)
- Network/mDNS (Chromecast, smart TVs, printers, etc.)
- UPnP/SSDP (media devices, routers)

Installation:
    pip install bleak            # Bluetooth LE
    pip install zeroconf         # mDNS/Bonjour
    pip install async-upnp-client  # UPnP (optional)

Usage:
    "scan for devices" / "find devices" - Discover all devices
    "scan bluetooth" - Scan Bluetooth only
    "list devices" / "show devices" - Show discovered devices
    "connect to <device>" - Connect to a device
    "device status" - Show discovery status
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """A discovered smart device."""
    name: str
    address: str  # MAC for BT, IP for network
    device_type: str  # bluetooth, network, upnp
    manufacturer: str | None = None
    model: str | None = None
    services: list[str] = field(default_factory=list)
    rssi: int | None = None  # Signal strength for BT
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Get display-friendly name."""
        if self.name and self.name != "Unknown":
            return self.name
        if self.manufacturer:
            return f"{self.manufacturer} Device"
        return self.address


class DeviceDiscoveryPlugin(BasePlugin):
    """
    Device discovery plugin - scan your home for smart devices.

    Supports Bluetooth LE, mDNS/Bonjour, and UPnP discovery.
    Stores discovered devices for later control.
    """

    info = PluginInfo(
        name="devices",
        version="1.0.0",
        description="Scan and discover smart home devices (Bluetooth, network)",
        author="SafestClaw Community",
        keywords=[
            "scan", "devices", "bluetooth", "discover", "find devices",
            "list devices", "show devices", "connect", "smart home",
        ],
        patterns=[
            r"(?i)^(?:scan|search|find|discover)(?:\s+for)?\s+devices?",
            r"(?i)^scan\s+(?:for\s+)?bluetooth",
            r"(?i)^scan\s+(?:for\s+)?network",
            r"(?i)^(?:list|show|display)\s+devices?",
            r"(?i)^connect\s+(?:to\s+)?(.+)",
            r"(?i)^device(?:s)?\s+(?:status|info)",
            r"(?i)^forget\s+(?:device\s+)?(.+)",
        ],
        examples=[
            "scan for devices",
            "scan bluetooth",
            "list devices",
            "show devices",
            "connect to living room speaker",
            "device status",
        ],
    )

    def __init__(self):
        self.devices: dict[str, DiscoveredDevice] = {}
        self._engine: Any = None
        self._data_file: Path | None = None
        self._scanning = False

        # Check available backends
        self._has_bleak = False
        self._has_zeroconf = False
        self._has_upnp = False

    def on_load(self, engine: Any) -> None:
        """Initialize and check for available backends."""
        self._engine = engine
        self._data_file = engine.data_dir / "discovered_devices.json"

        # Check for bleak (Bluetooth LE)
        try:
            import bleak
            self._has_bleak = True
            logger.info("Bluetooth LE scanning available (bleak)")
        except ImportError:
            logger.info("bleak not installed - Bluetooth scanning unavailable")

        # Check for zeroconf (mDNS)
        try:
            import zeroconf
            self._has_zeroconf = True
            logger.info("mDNS/Bonjour scanning available (zeroconf)")
        except ImportError:
            logger.info("zeroconf not installed - mDNS scanning unavailable")

        # Check for UPnP
        try:
            import async_upnp_client
            self._has_upnp = True
            logger.info("UPnP scanning available")
        except ImportError:
            pass

        # Load saved devices
        self._load_devices()

    def _load_devices(self) -> None:
        """Load previously discovered devices."""
        if self._data_file and self._data_file.exists():
            try:
                data = json.loads(self._data_file.read_text())
                for addr, dev_data in data.items():
                    self.devices[addr] = DiscoveredDevice(**dev_data)
                logger.info(f"Loaded {len(self.devices)} saved devices")
            except Exception as e:
                logger.warning(f"Failed to load devices: {e}")

    def _save_devices(self) -> None:
        """Save discovered devices to disk."""
        if self._data_file:
            try:
                data = {addr: asdict(dev) for addr, dev in self.devices.items()}
                self._data_file.write_text(json.dumps(data, indent=2))
            except Exception as e:
                logger.warning(f"Failed to save devices: {e}")

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Handle device discovery commands."""
        text = params.get("raw_input", "").lower().strip()

        # Scan commands
        if any(kw in text for kw in ["scan for devices", "find devices", "discover devices", "search for devices"]):
            return await self._scan_all()

        if "scan bluetooth" in text or "scan bt" in text:
            return await self._scan_bluetooth()

        if "scan network" in text or "scan wifi" in text:
            return await self._scan_network()

        # List devices
        if any(kw in text for kw in ["list devices", "show devices", "display devices", "my devices"]):
            return self._list_devices()

        # Device status
        if "device status" in text or "devices status" in text or "device info" in text:
            return self._get_status()

        # Connect to device
        if text.startswith("connect to ") or text.startswith("connect "):
            device_name = text.replace("connect to ", "").replace("connect ", "").strip()
            return await self._connect_device(device_name)

        # Forget device
        if text.startswith("forget device ") or text.startswith("forget "):
            device_name = text.replace("forget device ", "").replace("forget ", "").strip()
            return self._forget_device(device_name)

        return self._get_status()

    async def _scan_all(self) -> str:
        """Scan all available methods."""
        if self._scanning:
            return "[yellow]Scan already in progress...[/yellow]"

        self._scanning = True
        results = ["[bold]Scanning for devices...[/bold]\n"]

        try:
            # Scan Bluetooth
            if self._has_bleak:
                bt_count = await self._scan_bluetooth_internal()
                results.append(f"Bluetooth: Found {bt_count} devices")

            # Scan network
            if self._has_zeroconf:
                net_count = await self._scan_network_internal()
                results.append(f"Network: Found {net_count} devices")

            # Save results
            self._save_devices()

            results.append(f"\n[green]Total: {len(self.devices)} devices discovered[/green]")
            results.append("\nSay 'list devices' to see them all.")

        finally:
            self._scanning = False

        return "\n".join(results)

    async def _scan_bluetooth(self) -> str:
        """Scan for Bluetooth devices only."""
        if not self._has_bleak:
            return (
                "[yellow]Bluetooth scanning not available.[/yellow]\n\n"
                "Install bleak:\n"
                "  pip install bleak"
            )

        if self._scanning:
            return "[yellow]Scan already in progress...[/yellow]"

        self._scanning = True
        try:
            count = await self._scan_bluetooth_internal()
            self._save_devices()
            return f"[green]Bluetooth scan complete. Found {count} devices.[/green]\n\nSay 'list devices' to see them."
        finally:
            self._scanning = False

    async def _scan_bluetooth_internal(self, timeout: float = 10.0) -> int:
        """Internal Bluetooth scan."""
        try:
            from bleak import BleakScanner

            logger.info(f"Scanning Bluetooth for {timeout}s...")

            devices = await BleakScanner.discover(timeout=timeout)
            count = 0

            for device in devices:
                # Get device details
                name = device.name or "Unknown"
                address = device.address

                # Try to get manufacturer data
                manufacturer = None
                services = []

                if device.metadata:
                    # Extract manufacturer from advertisement data
                    mfr_data = device.metadata.get("manufacturer_data", {})
                    if mfr_data:
                        # Common manufacturer IDs
                        mfr_ids = {
                            76: "Apple",
                            6: "Microsoft",
                            117: "Samsung",
                            224: "Google",
                            89: "Nordic Semiconductor",
                            343: "Xiaomi",
                            741: "Philips",
                            280: "IKEA",
                        }
                        for mfr_id in mfr_data.keys():
                            if mfr_id in mfr_ids:
                                manufacturer = mfr_ids[mfr_id]
                                break

                    # Get service UUIDs
                    service_uuids = device.metadata.get("uuids", [])
                    services = list(service_uuids)[:5]  # Limit to 5

                # Create/update device
                self.devices[address] = DiscoveredDevice(
                    name=name,
                    address=address,
                    device_type="bluetooth",
                    manufacturer=manufacturer,
                    services=services,
                    rssi=device.rssi if hasattr(device, 'rssi') else None,
                    last_seen=datetime.now().isoformat(),
                    metadata={"raw": str(device.metadata) if device.metadata else ""},
                )
                count += 1

            logger.info(f"Found {count} Bluetooth devices")
            return count

        except Exception as e:
            logger.error(f"Bluetooth scan failed: {e}")
            return 0

    async def _scan_network(self) -> str:
        """Scan for network devices via mDNS."""
        if not self._has_zeroconf:
            return (
                "[yellow]Network scanning not available.[/yellow]\n\n"
                "Install zeroconf:\n"
                "  pip install zeroconf"
            )

        if self._scanning:
            return "[yellow]Scan already in progress...[/yellow]"

        self._scanning = True
        try:
            count = await self._scan_network_internal()
            self._save_devices()
            return f"[green]Network scan complete. Found {count} devices.[/green]\n\nSay 'list devices' to see them."
        finally:
            self._scanning = False

    async def _scan_network_internal(self, timeout: float = 5.0) -> int:
        """Internal network/mDNS scan."""
        try:
            from zeroconf import ServiceBrowser, Zeroconf

            # Common service types to scan for
            service_types = [
                "_googlecast._tcp.local.",      # Chromecast
                "_airplay._tcp.local.",         # AirPlay (Apple TV, etc.)
                "_raop._tcp.local.",            # AirPlay audio
                "_spotify-connect._tcp.local.", # Spotify Connect
                "_hue._tcp.local.",             # Philips Hue
                "_homekit._tcp.local.",         # HomeKit devices
                "_ipp._tcp.local.",             # Printers
                "_http._tcp.local.",            # HTTP services
                "_smb._tcp.local.",             # SMB shares
                "_ssh._tcp.local.",             # SSH servers
                "_mqtt._tcp.local.",            # MQTT brokers
            ]

            discovered = {}

            class MyListener:
                def add_service(self, zc, service_type, name):
                    info = zc.get_service_info(service_type, name)
                    if info:
                        addresses = [str(addr) for addr in info.parsed_addresses()]
                        if addresses:
                            discovered[name] = {
                                "name": name.replace(f".{service_type}", ""),
                                "addresses": addresses,
                                "service_type": service_type,
                                "port": info.port,
                                "properties": dict(info.properties) if info.properties else {},
                            }

                def remove_service(self, zc, service_type, name):
                    pass

                def update_service(self, zc, service_type, name):
                    pass

            zc = Zeroconf()
            listener = MyListener()

            browsers = []
            for stype in service_types:
                try:
                    browsers.append(ServiceBrowser(zc, stype, listener))
                except Exception:
                    pass

            # Wait for discovery
            await asyncio.sleep(timeout)

            # Cleanup
            for browser in browsers:
                browser.cancel()
            zc.close()

            # Process discovered devices
            count = 0
            for name, data in discovered.items():
                address = data["addresses"][0] if data["addresses"] else name

                # Determine device type from service
                service = data["service_type"]
                device_name = data["name"]
                manufacturer = None

                if "googlecast" in service:
                    manufacturer = "Google"
                elif "airplay" in service or "raop" in service:
                    manufacturer = "Apple"
                elif "hue" in service:
                    manufacturer = "Philips"
                elif "homekit" in service:
                    manufacturer = "HomeKit"

                self.devices[address] = DiscoveredDevice(
                    name=device_name,
                    address=address,
                    device_type="network",
                    manufacturer=manufacturer,
                    services=[service],
                    last_seen=datetime.now().isoformat(),
                    metadata={
                        "port": data["port"],
                        "properties": {k.decode() if isinstance(k, bytes) else k:
                                      v.decode() if isinstance(v, bytes) else v
                                      for k, v in data["properties"].items()},
                    },
                )
                count += 1

            logger.info(f"Found {count} network devices")
            return count

        except Exception as e:
            logger.error(f"Network scan failed: {e}")
            return 0

    def _list_devices(self) -> str:
        """List all discovered devices."""
        if not self.devices:
            return (
                "No devices discovered yet.\n\n"
                "Say 'scan for devices' to find devices on your network."
            )

        lines = ["[bold]Discovered Devices[/bold]\n"]

        # Group by type
        bt_devices = [d for d in self.devices.values() if d.device_type == "bluetooth"]
        net_devices = [d for d in self.devices.values() if d.device_type == "network"]

        if bt_devices:
            lines.append("[cyan]Bluetooth:[/cyan]")
            for dev in sorted(bt_devices, key=lambda d: d.rssi or -100, reverse=True):
                rssi = f" ({dev.rssi} dBm)" if dev.rssi else ""
                mfr = f" [{dev.manufacturer}]" if dev.manufacturer else ""
                lines.append(f"  • {dev.display_name}{mfr}{rssi}")
                lines.append(f"    [dim]{dev.address}[/dim]")
            lines.append("")

        if net_devices:
            lines.append("[cyan]Network:[/cyan]")
            for dev in sorted(net_devices, key=lambda d: d.name):
                mfr = f" [{dev.manufacturer}]" if dev.manufacturer else ""
                svc = dev.services[0].replace("._tcp.local.", "") if dev.services else ""
                lines.append(f"  • {dev.display_name}{mfr}")
                lines.append(f"    [dim]{dev.address} ({svc})[/dim]")
            lines.append("")

        lines.append(f"[dim]Total: {len(self.devices)} devices[/dim]")
        return "\n".join(lines)

    def _get_status(self) -> str:
        """Get device discovery status."""
        bt_status = "[green]available[/green]" if self._has_bleak else "[dim]not installed[/dim]"
        net_status = "[green]available[/green]" if self._has_zeroconf else "[dim]not installed[/dim]"
        upnp_status = "[green]available[/green]" if self._has_upnp else "[dim]not installed[/dim]"

        bt_count = len([d for d in self.devices.values() if d.device_type == "bluetooth"])
        net_count = len([d for d in self.devices.values() if d.device_type == "network"])

        return (
            f"[bold]Device Discovery Status[/bold]\n\n"
            f"Backends:\n"
            f"  Bluetooth (bleak): {bt_status}\n"
            f"  Network (zeroconf): {net_status}\n"
            f"  UPnP: {upnp_status}\n\n"
            f"Discovered devices:\n"
            f"  Bluetooth: {bt_count}\n"
            f"  Network: {net_count}\n"
            f"  Total: {len(self.devices)}\n\n"
            f"Commands:\n"
            f"  • 'scan for devices' - Discover all devices\n"
            f"  • 'scan bluetooth' - Bluetooth only\n"
            f"  • 'scan network' - Network/mDNS only\n"
            f"  • 'list devices' - Show discovered devices"
        )

    async def _connect_device(self, name: str) -> str:
        """Connect to a discovered device."""
        # Find device by name (fuzzy match)
        name_lower = name.lower()
        matching = None

        for dev in self.devices.values():
            if name_lower in dev.name.lower() or name_lower in dev.address.lower():
                matching = dev
                break

        if not matching:
            return f"[yellow]Device not found: {name}[/yellow]\n\nSay 'list devices' to see available devices."

        # For now, just show device info
        # TODO: Implement actual connection based on device type
        lines = [
            f"[bold]Device: {matching.display_name}[/bold]\n",
            f"Address: {matching.address}",
            f"Type: {matching.device_type}",
        ]

        if matching.manufacturer:
            lines.append(f"Manufacturer: {matching.manufacturer}")
        if matching.services:
            lines.append(f"Services: {', '.join(matching.services[:3])}")
        if matching.rssi:
            lines.append(f"Signal: {matching.rssi} dBm")

        lines.append("\n[dim]Device connection not yet implemented.[/dim]")

        return "\n".join(lines)

    def _forget_device(self, name: str) -> str:
        """Remove a device from the list."""
        name_lower = name.lower()

        for addr, dev in list(self.devices.items()):
            if name_lower in dev.name.lower() or name_lower in addr.lower():
                del self.devices[addr]
                self._save_devices()
                return f"[green]Forgot device: {dev.display_name}[/green]"

        return f"[yellow]Device not found: {name}[/yellow]"
