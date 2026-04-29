"""
SafestClaw Piper TTS Plugin - Text-to-speech using Piper.

Piper is a fast, local neural text-to-speech system.
https://github.com/rhasspy/piper

Installation:
    pip install piper-tts

Or install piper binary and models manually.

Usage:
    "enable voice" / "turn on voice" - Enable TTS
    "disable voice" / "turn off voice" - Disable TTS
    "say hello" / "speak this text" - Speak specific text
"""

import asyncio
import logging
import platform
import shutil
from pathlib import Path
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class PiperTTSPlugin(BasePlugin):
    """
    Text-to-speech plugin using Piper.

    Piper runs entirely locally - no cloud APIs needed.
    Perfect for privacy-first voice output.
    """

    info = PluginInfo(
        name="piper",
        version="1.0.0",
        description="Text-to-speech using Piper (local, privacy-first)",
        author="SafestClaw Community",
        keywords=[
            "voice", "speak", "say", "tts", "piper",
            "enable voice", "disable voice", "turn on voice", "turn off voice",
        ],
        patterns=[
            r"(?i)^(?:enable|turn\s+on|start)\s+(?:the\s+)?voice",
            r"(?i)^(?:disable|turn\s+off|stop)\s+(?:the\s+)?voice",
            r"(?i)^(?:say|speak|read(?:\s+out)?)\s+(.+)",
            r"(?i)^voice\s+(on|off|status)",
        ],
        examples=[
            "enable voice",
            "turn on voice",
            "disable voice",
            "say hello there",
            "speak this is a test",
            "voice status",
        ],
    )

    def __init__(self):
        self.enabled = False
        self.piper_path: Path | None = None
        self.model_path: Path | None = None
        self._engine: Any = None
        self._greeted = False

    def on_load(self, engine: Any) -> None:
        """Called when plugin loads. Check for Piper installation."""
        self._engine = engine

        # Check for piper in PATH or common locations
        self.piper_path = self._find_piper()

        if self.piper_path:
            logger.info(f"Piper found at: {self.piper_path}")
        else:
            logger.info("Piper not found - TTS will use fallback or be unavailable")

        # Check for piper-tts Python package
        try:
            import piper
            self._has_piper_python = True
            logger.info("piper-tts Python package available")
        except ImportError:
            self._has_piper_python = False

    def _find_piper(self) -> Path | None:
        """Find piper executable."""
        # Check PATH
        piper_cmd = shutil.which("piper")
        if piper_cmd:
            return Path(piper_cmd)

        # Check common locations
        common_paths = [
            Path.home() / ".local" / "bin" / "piper",
            Path("/usr/local/bin/piper"),
            Path("/usr/bin/piper"),
            Path.home() / "piper" / "piper",
        ]

        # Add Homebrew paths on macOS
        if platform.system() == "Darwin":
            common_paths.extend([
                Path("/opt/homebrew/bin/piper"),  # Apple Silicon
            ])

        for path in common_paths:
            if path.exists():
                return path

        return None

    def _find_model(self) -> Path | None:
        """Find a Piper voice model."""
        # Check common model locations
        model_dirs = [
            Path.home() / ".local" / "share" / "piper" / "voices",
            Path.home() / "piper" / "voices",
            Path.home() / ".piper" / "voices",
            Path("/usr/share/piper/voices"),
        ]

        for model_dir in model_dirs:
            if model_dir.exists():
                # Look for .onnx files (Piper models)
                models = list(model_dir.glob("**/*.onnx"))
                if models:
                    return models[0]

        return None

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Handle voice commands."""
        text = params.get("raw_input", "").lower().strip()

        # Enable voice
        if any(kw in text for kw in ["enable voice", "turn on voice", "start voice", "voice on"]):
            return await self._enable_voice(user_id)

        # Disable voice
        if any(kw in text for kw in ["disable voice", "turn off voice", "stop voice", "voice off"]):
            return self._disable_voice()

        # Status check
        if "voice status" in text or text == "voice":
            return self._get_status()

        # Say/speak command
        if text.startswith(("say ", "speak ", "read ")):
            # Extract the text to speak
            for prefix in ["say ", "speak ", "read out ", "read "]:
                if text.startswith(prefix):
                    speech_text = params.get("raw_input", "")[len(prefix):].strip()
                    break
            else:
                speech_text = text

            if self.enabled:
                await self._speak(speech_text)
                return f"[dim](Speaking: {speech_text[:50]}{'...' if len(speech_text) > 50 else ''})[/dim]"
            else:
                return "Voice is disabled. Say 'enable voice' to turn it on."

        return self._get_status()

    async def _enable_voice(self, user_id: str) -> str:
        """Enable voice output and greet the user."""
        if not self.piper_path and not self._has_piper_python:
            return (
                "[yellow]Piper not installed.[/yellow]\n\n"
                "To install Piper:\n"
                "  pip install piper-tts\n\n"
                "Or download from: https://github.com/rhasspy/piper/releases"
            )

        self.enabled = True

        # Get user's name from engine config or memory, default to "Tony"
        name = "Tony"
        if self._engine:
            # Try to get from config
            name = self._engine.config.get("safestclaw", {}).get("user_name", "Tony")

        # Greet on first enable
        greeting = f"Hello {name}, how may I help you?"

        # Speak the greeting
        await self._speak(greeting)

        return f"[green]Voice enabled.[/green] {greeting}"

    def _disable_voice(self) -> str:
        """Disable voice output."""
        self.enabled = False
        self._greeted = False
        return "[yellow]Voice disabled.[/yellow]"

    def _get_status(self) -> str:
        """Get current voice status."""
        status = "[green]enabled[/green]" if self.enabled else "[dim]disabled[/dim]"
        piper_status = "[green]installed[/green]" if (self.piper_path or self._has_piper_python) else "[red]not found[/red]"

        return (
            f"**Voice Status**\n"
            f"  Status: {status}\n"
            f"  Piper: {piper_status}\n"
            f"\nCommands:\n"
            f"  • 'enable voice' - Turn on text-to-speech\n"
            f"  • 'disable voice' - Turn off text-to-speech\n"
            f"  • 'say <text>' - Speak specific text"
        )

    async def _speak(self, text: str) -> bool:
        """
        Speak text using Piper.

        Returns True if successful.
        """
        if not text:
            return False

        # Try Python piper-tts first
        if self._has_piper_python:
            try:
                return await self._speak_python(text)
            except Exception as e:
                logger.warning(f"Python piper failed: {e}, trying CLI")

        # Fall back to CLI piper
        if self.piper_path:
            try:
                return await self._speak_cli(text)
            except Exception as e:
                logger.error(f"Piper CLI failed: {e}")

        # Final fallback - try system TTS
        return await self._speak_fallback(text)

    async def _speak_python(self, text: str) -> bool:
        """Speak using piper-tts Python package."""
        try:
            import tempfile
            import wave

            import piper

            # Find a model
            model_path = self._find_model()
            if not model_path:
                # piper-tts can auto-download models
                logger.info("No local model found, piper-tts may download one")

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def _synthesize():
                # Create voice
                voice = piper.PiperVoice.load(str(model_path) if model_path else "en_US-lessac-medium")

                # Synthesize to temp file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name

                with wave.open(temp_path, "wb") as wav_file:
                    voice.synthesize(text, wav_file)

                return temp_path

            temp_path = await loop.run_in_executor(None, _synthesize)

            # Play the audio
            await self._play_audio(temp_path)

            # Clean up
            Path(temp_path).unlink(missing_ok=True)
            return True

        except Exception as e:
            logger.error(f"Python TTS failed: {e}")
            raise

    async def _speak_cli(self, text: str) -> bool:
        """Speak using piper CLI."""
        try:
            model = self._find_model()
            if not model:
                logger.warning("No Piper model found")
                return False

            # Piper CLI: echo "text" | piper --model model.onnx --output_file out.wav
            process = await asyncio.create_subprocess_exec(
                str(self.piper_path),
                "--model", str(model),
                "--output-raw",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate(text.encode())

            if process.returncode == 0 and stdout:
                # Play raw audio using aplay or similar
                await self._play_raw_audio(stdout)
                return True

            if stderr:
                logger.warning(f"Piper stderr: {stderr.decode()}")

            return False

        except Exception as e:
            logger.error(f"CLI TTS failed: {e}")
            raise

    async def _speak_fallback(self, text: str) -> bool:
        """Fallback TTS using system tools (espeak, say, etc.)."""
        # Try common TTS tools
        fallbacks = [
            ("espeak", ["-s", "150"]),  # Linux
            ("espeak-ng", ["-s", "150"]),  # Linux (newer)
            ("say", []),  # macOS
            ("spd-say", []),  # Linux speech-dispatcher
        ]

        for cmd, args in fallbacks:
            if shutil.which(cmd):
                try:
                    process = await asyncio.create_subprocess_exec(
                        cmd, *args, text,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await process.wait()
                    return process.returncode == 0
                except Exception:
                    continue

        logger.warning("No TTS fallback available")
        return False

    async def _play_audio(self, path: str) -> None:
        """Play an audio file."""
        players = [
            ("aplay", ["-q"]),  # ALSA (Linux)
            ("paplay", []),  # PulseAudio (Linux)
            ("afplay", []),  # macOS
            ("play", ["-q"]),  # SoX
        ]

        for cmd, args in players:
            if shutil.which(cmd):
                try:
                    process = await asyncio.create_subprocess_exec(
                        cmd, *args, path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await process.wait()
                    return
                except Exception:
                    continue

    async def _play_raw_audio(self, data: bytes, sample_rate: int = 22050) -> None:
        """Play raw audio data."""
        # aplay can play raw audio directly from stdin (Linux/ALSA)
        if shutil.which("aplay"):
            try:
                process = await asyncio.create_subprocess_exec(
                    "aplay",
                    "-q",
                    "-f", "S16_LE",
                    "-r", str(sample_rate),
                    "-c", "1",
                    "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.communicate(data)
                return
            except Exception as e:
                logger.warning(f"aplay raw playback failed: {e}")

        # sox play can handle raw audio from stdin (cross-platform, macOS via brew)
        if shutil.which("play"):
            try:
                process = await asyncio.create_subprocess_exec(
                    "play",
                    "-q",
                    "-t", "raw",
                    "-r", str(sample_rate),
                    "-e", "signed-integer",
                    "-b", "16",
                    "-c", "1",
                    "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.communicate(data)
                return
            except Exception as e:
                logger.warning(f"sox play raw playback failed: {e}")

        # afplay requires a file on disk (macOS)
        if shutil.which("afplay"):
            try:
                import tempfile
                import wave

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name

                with wave.open(temp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(sample_rate)
                    wf.writeframes(data)

                process = await asyncio.create_subprocess_exec(
                    "afplay", temp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()
                Path(temp_path).unlink(missing_ok=True)
                return
            except Exception as e:
                logger.warning(f"afplay raw playback failed: {e}")

        logger.error("No audio player available for raw audio playback")

    async def speak_response(self, response: str) -> None:
        """
        Speak a SafestClaw response.

        Call this from engine/channel to voice responses when enabled.
        """
        if self.enabled and response:
            # Strip Rich markup for TTS
            clean_text = self._strip_markup(response)
            if clean_text:
                await self._speak(clean_text)

    def _strip_markup(self, text: str) -> str:
        """Strip Rich markup tags from text."""
        import re
        # Remove [tag] and [/tag] patterns
        return re.sub(r'\[/?[^\]]+\]', '', text)
