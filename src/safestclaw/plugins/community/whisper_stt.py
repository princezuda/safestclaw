"""
SafestClaw Whisper STT Plugin - Speech-to-text using Whisper.

Whisper is OpenAI's speech recognition model, available locally via:
- faster-whisper (recommended, fastest)
- whisper.cpp
- openai-whisper (original)

Installation:
    pip install faster-whisper

Or for whisper.cpp, download from: https://github.com/ggerganov/whisper.cpp

Usage:
    "enable listening" / "start listening" - Enable voice input
    "disable listening" / "stop listening" - Disable voice input
    "listen" - Record and transcribe a single command
"""

import asyncio
import logging
import platform
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from safestclaw.plugins.base import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class WhisperSTTPlugin(BasePlugin):
    """
    Speech-to-text plugin using Whisper.

    Runs entirely locally - no cloud APIs needed.
    Perfect for privacy-first voice input.
    """

    info = PluginInfo(
        name="whisper",
        version="1.0.0",
        description="Speech-to-text using Whisper (local, privacy-first)",
        author="SafestClaw Community",
        keywords=[
            "listen", "listening", "voice input", "stt", "whisper",
            "enable listening", "disable listening", "start listening", "stop listening",
            "transcribe", "dictate",
        ],
        patterns=[
            r"(?i)^(?:enable|turn\s+on|start)\s+listening",
            r"(?i)^(?:disable|turn\s+off|stop)\s+listening",
            r"(?i)^listen(?:ing)?(?:\s+mode)?$",
            r"(?i)^(?:transcribe|dictate)(?:\s+(.+))?",
            r"(?i)^whisper\s+(on|off|status)",
        ],
        examples=[
            "enable listening",
            "start listening",
            "disable listening",
            "listen",
            "whisper status",
            "transcribe audio.wav",
        ],
    )

    def __init__(self):
        self.enabled = False
        self.listening = False
        self._engine: Any = None
        self._whisper_model: Any = None
        self._model_name = "base"  # tiny, base, small, medium, large
        self._has_faster_whisper = False
        self._has_whisper = False
        self._whisper_cpp_path: Path | None = None
        self._on_transcription: Callable[[str], None] | None = None

    def on_load(self, engine: Any) -> None:
        """Called when plugin loads. Check for Whisper installation."""
        self._engine = engine

        # Check for faster-whisper (recommended)
        try:
            import faster_whisper
            self._has_faster_whisper = True
            logger.info("faster-whisper available")
        except ImportError:
            pass

        # Check for openai-whisper
        try:
            import whisper
            self._has_whisper = True
            logger.info("openai-whisper available")
        except ImportError:
            pass

        # Check for whisper.cpp
        self._whisper_cpp_path = self._find_whisper_cpp()
        if self._whisper_cpp_path:
            logger.info(f"whisper.cpp found at: {self._whisper_cpp_path}")

        # Get model preference from config
        if engine.config:
            self._model_name = engine.config.get("whisper", {}).get("model", "base")

    def _find_whisper_cpp(self) -> Path | None:
        """Find whisper.cpp executable."""
        # Check PATH
        for name in ["whisper", "whisper-cpp", "main"]:
            cmd = shutil.which(name)
            if cmd and "whisper" in cmd.lower():
                return Path(cmd)

        # Check common locations
        common_paths = [
            Path.home() / "whisper.cpp" / "main",
            Path.home() / ".local" / "bin" / "whisper",
            Path("/usr/local/bin/whisper"),
        ]

        # Add Homebrew paths on macOS
        if platform.system() == "Darwin":
            common_paths.extend([
                Path("/opt/homebrew/bin/whisper"),  # Apple Silicon
                Path("/opt/homebrew/bin/whisper-cpp"),
            ])

        for path in common_paths:
            if path.exists():
                return path

        return None

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str,
        channel: str,
        engine: Any,
    ) -> str:
        """Handle voice input commands."""
        text = params.get("raw_input", "").lower().strip()

        # Enable listening
        if any(kw in text for kw in ["enable listening", "turn on listening", "start listening", "whisper on"]):
            return await self._enable_listening()

        # Disable listening
        if any(kw in text for kw in ["disable listening", "turn off listening", "stop listening", "whisper off"]):
            return self._disable_listening()

        # Status check
        if "whisper status" in text or text == "whisper":
            return self._get_status()

        # Single listen command
        if text in ["listen", "listening", "listen mode"]:
            if not self.enabled:
                return "Listening is disabled. Say 'enable listening' to turn it on."
            return await self._listen_once(channel, engine)

        # Transcribe file
        if text.startswith("transcribe "):
            file_path = text[len("transcribe "):].strip()
            return await self._transcribe_file(file_path)

        return self._get_status()

    async def _enable_listening(self) -> str:
        """Enable voice input."""
        if not self._has_faster_whisper and not self._has_whisper and not self._whisper_cpp_path:
            return (
                "[yellow]Whisper not installed.[/yellow]\n\n"
                "To install (pick one):\n"
                "  pip install faster-whisper  [bold](recommended)[/bold]\n"
                "  pip install openai-whisper\n\n"
                "Or download whisper.cpp from:\n"
                "  https://github.com/ggerganov/whisper.cpp"
            )

        # Check for audio recording capability
        if not self._can_record():
            hint = "  Or ensure 'arecord' (Linux) or 'rec' (SoX) is available."
            if platform.system() == "Darwin":
                hint = "  Or install SoX: brew install sox"
            return (
                "[yellow]Audio recording not available.[/yellow]\n\n"
                "Install one of:\n"
                "  pip install sounddevice\n"
                "  pip install pyaudio\n\n"
                + hint
            )

        self.enabled = True

        # Load model in background
        asyncio.create_task(self._load_model())

        return (
            "[green]Listening enabled.[/green]\n\n"
            f"Model: {self._model_name}\n"
            "Say 'listen' to record a voice command.\n"
            "Say 'disable listening' to turn off."
        )

    def _disable_listening(self) -> str:
        """Disable voice input."""
        self.enabled = False
        self.listening = False
        return "[yellow]Listening disabled.[/yellow]"

    def _get_status(self) -> str:
        """Get current listening status."""
        status = "[green]enabled[/green]" if self.enabled else "[dim]disabled[/dim]"

        whisper_status = "not found"
        if self._has_faster_whisper:
            whisper_status = "[green]faster-whisper[/green]"
        elif self._has_whisper:
            whisper_status = "[green]openai-whisper[/green]"
        elif self._whisper_cpp_path:
            whisper_status = "[green]whisper.cpp[/green]"

        recording = "[green]available[/green]" if self._can_record() else "[red]not available[/red]"

        return (
            f"**Whisper Voice Input**\n"
            f"  Status: {status}\n"
            f"  Backend: {whisper_status}\n"
            f"  Model: {self._model_name}\n"
            f"  Recording: {recording}\n"
            f"\nCommands:\n"
            f"  - 'enable listening' - Turn on voice input\n"
            f"  - 'disable listening' - Turn off voice input\n"
            f"  - 'listen' - Record and transcribe a command\n"
            f"  - 'transcribe <file>' - Transcribe an audio file"
        )

    def _can_record(self) -> bool:
        """Check if audio recording is available."""
        # Check for sounddevice (cross-platform)
        try:
            import sounddevice
            return True
        except ImportError:
            pass

        # Check for pyaudio (cross-platform)
        try:
            import pyaudio
            return True
        except ImportError:
            pass

        # Check for arecord (Linux/ALSA)
        if shutil.which("arecord"):
            return True

        # Check for sox rec (cross-platform, macOS via `brew install sox`)
        if shutil.which("rec"):
            return True

        # Check for ffmpeg (cross-platform, macOS via `brew install ffmpeg`)
        if shutil.which("ffmpeg"):
            return True

        return False

    async def _load_model(self) -> None:
        """Load Whisper model in background."""
        if self._whisper_model is not None:
            return

        try:
            if self._has_faster_whisper:
                from faster_whisper import WhisperModel

                # Run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                self._whisper_model = await loop.run_in_executor(
                    None,
                    lambda: WhisperModel(self._model_name, device="cpu", compute_type="int8")
                )
                logger.info(f"Loaded faster-whisper model: {self._model_name}")

            elif self._has_whisper:
                import whisper

                loop = asyncio.get_event_loop()
                self._whisper_model = await loop.run_in_executor(
                    None,
                    lambda: whisper.load_model(self._model_name)
                )
                logger.info(f"Loaded whisper model: {self._model_name}")

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")

    async def _listen_once(self, channel: str, engine: Any) -> str:
        """Record audio and transcribe a single command."""
        if not self.enabled:
            return "Listening is not enabled."

        # Record audio
        self.listening = True
        audio_path = await self._record_audio()
        self.listening = False

        if not audio_path:
            return "[red]Failed to record audio.[/red]"

        # Transcribe
        try:
            transcription = await self._transcribe(audio_path)

            if not transcription:
                return "[yellow]Could not transcribe audio. Please try again.[/yellow]"

            # Clean up temp file
            Path(audio_path).unlink(missing_ok=True)

            # Show what was heard
            result = f"[dim]Heard:[/dim] {transcription}\n\n"

            # Process the transcribed command through the engine
            if engine and transcription.strip():
                response = await engine.handle_message(
                    text=transcription,
                    channel=channel,
                    user_id="voice_user",
                )
                result += response

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return f"[red]Transcription failed: {e}[/red]"

    async def _record_audio(self, duration: float = 5.0, sample_rate: int = 16000) -> str | None:
        """
        Record audio from microphone.

        Returns path to temporary WAV file.
        """
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_path = temp_file.name
        temp_file.close()

        # Try sounddevice first
        try:
            import wave

            import numpy as np
            import sounddevice as sd

            logger.info(f"Recording {duration}s of audio...")

            # Record
            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(
                None,
                lambda: sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
            )

            # Wait for recording to complete
            await loop.run_in_executor(None, sd.wait)

            # Save to WAV
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())

            return temp_path

        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"sounddevice recording failed: {e}")

        # Try arecord (Linux/ALSA)
        if shutil.which("arecord"):
            try:
                process = await asyncio.create_subprocess_exec(
                    "arecord",
                    "-f", "S16_LE",
                    "-r", str(sample_rate),
                    "-c", "1",
                    "-d", str(int(duration)),
                    temp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()

                if process.returncode == 0:
                    return temp_path

            except Exception as e:
                logger.warning(f"arecord failed: {e}")

        # Try sox rec (cross-platform, works on macOS with `brew install sox`)
        if shutil.which("rec"):
            try:
                process = await asyncio.create_subprocess_exec(
                    "rec",
                    "-r", str(sample_rate),
                    "-c", "1",
                    "-b", "16",
                    temp_path,
                    "trim", "0", str(duration),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()

                if process.returncode == 0:
                    return temp_path

            except Exception as e:
                logger.warning(f"sox rec failed: {e}")

        # Try ffmpeg (cross-platform, works on macOS with `brew install ffmpeg`)
        if shutil.which("ffmpeg"):
            try:
                # On macOS, use avfoundation; on Linux, use alsa/pulse
                if platform.system() == "Darwin":
                    input_args = ["-f", "avfoundation", "-i", ":default"]
                else:
                    input_args = ["-f", "alsa", "-i", "default"]

                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    *input_args,
                    "-t", str(duration),
                    "-ar", str(sample_rate),
                    "-ac", "1",
                    "-sample_fmt", "s16",
                    temp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()

                if process.returncode == 0:
                    return temp_path

            except Exception as e:
                logger.warning(f"ffmpeg recording failed: {e}")

        # Clean up on failure
        Path(temp_path).unlink(missing_ok=True)
        return None

    async def _transcribe(self, audio_path: str) -> str | None:
        """Transcribe audio file to text."""
        # Ensure model is loaded
        if self._whisper_model is None and (self._has_faster_whisper or self._has_whisper):
            await self._load_model()

        # Try faster-whisper
        if self._has_faster_whisper and self._whisper_model:
            try:
                loop = asyncio.get_event_loop()

                def _transcribe():
                    segments, _ = self._whisper_model.transcribe(audio_path, beam_size=5)
                    return " ".join(segment.text for segment in segments)

                result = await loop.run_in_executor(None, _transcribe)
                return result.strip()

            except Exception as e:
                logger.error(f"faster-whisper transcription failed: {e}")

        # Try openai-whisper
        if self._has_whisper and self._whisper_model:
            try:
                import whisper

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: whisper.transcribe(self._whisper_model, audio_path)
                )
                return result["text"].strip()

            except Exception as e:
                logger.error(f"whisper transcription failed: {e}")

        # Try whisper.cpp
        if self._whisper_cpp_path:
            return await self._transcribe_cpp(audio_path)

        return None

    async def _transcribe_cpp(self, audio_path: str) -> str | None:
        """Transcribe using whisper.cpp."""
        # Find model file
        model_paths = [
            Path.home() / ".cache" / "whisper" / f"ggml-{self._model_name}.bin",
            Path.home() / "whisper.cpp" / "models" / f"ggml-{self._model_name}.bin",
            Path(f"/usr/share/whisper/ggml-{self._model_name}.bin"),
        ]

        model_path = None
        for path in model_paths:
            if path.exists():
                model_path = path
                break

        if not model_path:
            logger.warning(f"whisper.cpp model not found: ggml-{self._model_name}.bin")
            return None

        try:
            process = await asyncio.create_subprocess_exec(
                str(self._whisper_cpp_path),
                "-m", str(model_path),
                "-f", audio_path,
                "--no-timestamps",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return stdout.decode().strip()

            logger.warning(f"whisper.cpp stderr: {stderr.decode()}")

        except Exception as e:
            logger.error(f"whisper.cpp failed: {e}")

        return None

    async def _transcribe_file(self, file_path: str) -> str:
        """Transcribe an audio file."""
        path = Path(file_path.strip('"\''))

        # Resolve to prevent path traversal and restrict to home directory
        try:
            resolved = path.expanduser().resolve()
            home = Path.home().resolve()
            if not (resolved == home or resolved.is_relative_to(home)):
                return "[red]Access denied: file is outside home directory[/red]"
        except (OSError, ValueError):
            return "[red]Invalid file path[/red]"

        if not resolved.exists():
            return f"[red]File not found: {path}[/red]"

        if resolved.suffix.lower() not in [".wav", ".mp3", ".flac", ".ogg", ".m4a"]:
            return f"[yellow]Unsupported format: {resolved.suffix}[/yellow]\nSupported: wav, mp3, flac, ogg, m4a"

        # Reject symlinks pointing outside home directory
        if resolved.is_symlink():
            link_target = resolved.resolve(strict=True)
            if not link_target.is_relative_to(home):
                return "[red]Access denied: symlink target is outside home directory[/red]"

        transcription = await self._transcribe(str(resolved))

        if transcription:
            return f"**Transcription:**\n{transcription}"
        else:
            return "[red]Transcription failed.[/red]"
