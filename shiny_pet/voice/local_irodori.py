"""Application-managed Irodori-TTS-Server runtime."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from shiny_pet.i18n import tr, trf

from .local_asr import _python_venv_command

LOCAL_IRODORI_HOST = "127.0.0.1"
LOCAL_IRODORI_PORT = 8088
LOCAL_IRODORI_MODEL = "irodori-tts"
LOCAL_IRODORI_CHECKPOINT = "Aratako/Irodori-TTS-v4.1-Small"
LOCAL_IRODORI_API_URL = f"http://{LOCAL_IRODORI_HOST}:{LOCAL_IRODORI_PORT}"

_RUNTIME_VERSION = "1"
_SERVER_REVISION = "841fb7c6ec57729c56b9b75c0ef2562249b13a10"
_IRODORI_REVISION = "8ca3acb58ab4e19ad6d594aaed6bafe3e88f7f71"
_DACVAE_REVISION = "414c20785fc3a28373073ea8ef7a1316eeeaca6e"
_SERVER_REQUIREMENT = (
    "irodori-tts-server @ git+https://github.com/Aratako/"
    f"Irodori-TTS-Server.git@{_SERVER_REVISION}"
)
_IRODORI_REQUIREMENT = (
    "irodori-tts @ git+https://github.com/Aratako/"
    f"Irodori-TTS.git@{_IRODORI_REVISION}"
)
_DACVAE_REQUIREMENT = (
    "dacvae @ git+https://github.com/facebookresearch/"
    f"dacvae.git@{_DACVAE_REVISION}"
)
_REFERENCE_EXTENSIONS = (".wav", ".flac", ".ogg", ".m4a", ".mp3")


class LocalIrodoriInstallCancelled(RuntimeError):
    """Raised when the user cancels local Irodori installation."""


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _irodori_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return whether the endpoint is the expected, loaded Irodori server."""
    try:
        with urlopen(f"http://{host}:{port}/health", timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError, TypeError):
        return False
    model = payload.get("model", {})
    runtime = payload.get("runtime", {})
    return bool(
        payload.get("status") == "ok"
        and model.get("id") == LOCAL_IRODORI_MODEL
        and runtime.get("loaded") is True
    )


class LocalIrodoriTTSServer:
    """Install and own an isolated official Irodori-TTS-Server process."""

    def __init__(self, runtime_dir: Path, *, port: int = LOCAL_IRODORI_PORT) -> None:
        self.runtime_dir = runtime_dir.resolve()
        self.host = LOCAL_IRODORI_HOST
        self.port = port
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def python(self) -> Path:
        if sys.platform == "win32":
            return self.runtime_dir / ".venv" / "Scripts" / "python.exe"
        return self.runtime_dir / ".venv" / "bin" / "python"

    @property
    def installed(self) -> bool:
        try:
            version = (self.runtime_dir / ".install-complete").read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return False
        return version == _RUNTIME_VERSION and self.python.is_file()

    @staticmethod
    def _run(
        command: list[str],
        cwd: Path,
        cancel: threading.Event,
        progress: Callable[[str], None],
    ) -> None:
        if cancel.is_set():
            raise LocalIrodoriInstallCancelled()
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        while True:
            if cancel.is_set():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise LocalIrodoriInstallCancelled()
            try:
                output, _stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        decoded = output.decode(errors="replace").strip()
        if process.returncode:
            raise RuntimeError(
                decoded[-3000:] or trf("安裝指令失敗（{code}）", code=process.returncode)
            )
        if decoded:
            progress(decoded[-700:])

    def _write_environment(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        env = "\n".join((
            f"IRODORI_HOST={self.host}",
            f"IRODORI_PORT={self.port}",
            f"IRODORI_HF_CHECKPOINT={LOCAL_IRODORI_CHECKPOINT}",
            "IRODORI_MODEL_NAME=irodori-tts",
            "IRODORI_MODEL_DEVICE=cuda",
            "IRODORI_CODEC_DEVICE=cuda",
            "IRODORI_MODEL_PRECISION=bf16",
            "IRODORI_CODEC_PRECISION=bf16",
            "IRODORI_PRELOAD=true",
            "IRODORI_VOICES_DIR=voices",
            "IRODORI_DEFAULT_RESPONSE_FORMAT=wav",
            "IRODORI_DEFAULT_NUM_STEPS=12",
            "IRODORI_DEFAULT_T_SCHEDULE_MODE=sway",
            "IRODORI_DEFAULT_SWAY_COEFF=-1.0",
            "IRODORI_MAX_CONCURRENT_SYNTHESIS=1",
            "IRODORI_ALLOW_NO_REF_VOICE=true",
            "",
        ))
        (self.runtime_dir / ".env").write_text(env, encoding="utf-8")

    @staticmethod
    def _ffmpeg() -> str | None:
        return shutil.which("ffmpeg")

    def sync_voices(self, reference_root: Path) -> tuple[str, ...]:
        """Expose numeric character references as person_NN server voices."""
        source_root = reference_root.expanduser().resolve()
        voice_root = self.runtime_dir / "voices"
        voice_root.mkdir(parents=True, exist_ok=True)
        if not source_root.is_dir():
            return ()
        prepared: list[str] = []
        for source in sorted(source_root.iterdir()):
            if not source.is_file() or not source.stem.isdigit():
                continue
            if source.suffix.lower() not in _REFERENCE_EXTENSIONS:
                continue
            voice_id = f"person_{int(source.stem):02d}"
            target = voice_root / f"{voice_id}.wav"
            if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
                prepared.append(voice_id)
                continue
            if source.suffix.lower() == ".wav":
                shutil.copy2(source, target)
            else:
                ffmpeg = self._ffmpeg()
                if not ffmpeg:
                    raise RuntimeError(trf(
                        "需要系統 FFmpeg 才能準備 Irodori 參考音訊：{filename}。"
                        "請先安裝 FFmpeg 並加入 PATH，或改用 WAV。",
                        filename=source.name,
                    ))
                completed = subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i",
                     str(source), "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                     str(target)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    check=False,
                )
                if completed.returncode or not target.is_file():
                    detail = completed.stderr.decode(errors="replace")[-1000:]
                    raise RuntimeError(trf(
                        "Irodori 參考音訊轉換失敗：{detail}", detail=detail
                    ))
            prepared.append(voice_id)
        return tuple(prepared)

    def install(
        self,
        reference_root: Path,
        cancel: threading.Event,
        progress: Callable[[str], None] | None = None,
    ) -> str:
        report = progress or (lambda _message: None)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / ".install-complete").unlink(missing_ok=True)
        self._write_environment()
        if not self.python.is_file():
            report(tr("正在建立 Irodori-TTS 獨立 Python 環境…"))
            self._run(
                [*_python_venv_command(), "-m", "venv", str(self.runtime_dir / ".venv")],
                self.runtime_dir,
                cancel,
                report,
            )
        self._run(
            [str(self.python), "-c",
             "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'"],
            self.runtime_dir,
            cancel,
            report,
        )
        report(tr("正在安裝 CUDA 12.8 PyTorch；下載量較大，請保持網路連線…"))
        # The PyTorch wheel index also mirrors a partial set of third-party
        # dependencies.  Using it as the sole index makes pip attempt to build
        # packages such as typing-extensions from source, while their build
        # requirements (for example flit_core) are not present there.  Resolve
        # ordinary dependencies from PyPI first, then install only the pinned
        # CUDA wheels from the PyTorch index without dependency resolution.
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             "--index-url", "https://pypi.org/simple",
             "filelock", "fsspec>=0.8.5", "jinja2", "networkx>=2.5.1",
             "sympy>=1.13.3", "typing-extensions>=4.10.0"],
            self.runtime_dir,
            cancel,
            report,
        )
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-deps", "torch==2.10.0", "torchaudio==2.10.0",
             "--index-url", "https://download.pytorch.org/whl/cu128"],
            self.runtime_dir,
            cancel,
            report,
        )
        # TorchCodec and TorchAO publish their Windows wheels to PyPI, not to
        # the PyTorch CUDA wheel index used above.
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             "torchcodec==0.10.0", "torchao==0.16.0"],
            self.runtime_dir,
            cancel,
            report,
        )
        self._run(
            [str(self.python), "-c",
             "import torch; assert torch.cuda.is_available(), 'NVIDIA CUDA is unavailable'"],
            self.runtime_dir,
            cancel,
            report,
        )
        if not shutil.which("git"):
            raise RuntimeError(tr(
                "安裝官方 Irodori-TTS-Server 需要 Git，請先安裝 Git for Windows。"
            ))
        report(tr("正在安裝官方 Irodori-TTS-Server 與推理元件…"))
        # DACVAE is declared through the upstream project's uv-only source table.
        # Install its locked revision explicitly so the pip-based managed runtime
        # works on a clean machine as well.
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             _DACVAE_REQUIREMENT],
            self.runtime_dir,
            cancel,
            report,
        )
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             _IRODORI_REQUIREMENT, "pydantic-settings>=2.6.0", "python-dotenv>=1.0.1",
             "python-multipart>=0.0.9", "uvicorn[standard]>=0.32.0"],
            self.runtime_dir,
            cancel,
            report,
        )
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-deps", _SERVER_REQUIREMENT],
            self.runtime_dir,
            cancel,
            report,
        )
        voices = self.sync_voices(reference_root)
        (self.runtime_dir / ".install-complete").write_text(
            _RUNTIME_VERSION + "\n", encoding="utf-8"
        )
        report(trf(
            "已準備 {count} 個人物聲線；正在下載並載入 v4.1 模型…",
            count=len(voices),
        ))
        self.ensure_running(reference_root, cancel)
        return self.api_url

    def ensure_running(
        self,
        reference_root: Path,
        cancel: threading.Event | None = None,
    ) -> None:
        if _port_open(self.host, self.port):
            if _irodori_ready(self.host, self.port):
                return
            raise RuntimeError(trf(
                "連接埠 {port} 已被其他服務占用，或 Irodori 模型尚未就緒。",
                port=self.port,
            ))
        if not self.installed:
            raise RuntimeError(tr(
                "本機 Irodori-TTS 尚未安裝，請先到 TTS 設定執行一鍵安裝。"
            ))
        self._write_environment()
        self.sync_voices(reference_root)
        with self._lock:
            if _port_open(self.host, self.port):
                if _irodori_ready(self.host, self.port):
                    return
                raise RuntimeError(trf(
                    "連接埠 {port} 已被其他服務占用，或 Irodori 模型尚未就緒。",
                    port=self.port,
                ))
            log_path = self.runtime_dir / "server.log"
            env = os.environ.copy()
            env["HF_HOME"] = str(self.runtime_dir / "huggingface")
            env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            with log_path.open("ab") as log:
                self._process = subprocess.Popen(
                    [str(self.python), "-m", "irodori_openai_tts", "--host", self.host,
                     "--port", str(self.port)],
                    cwd=str(self.runtime_dir),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if cancel is not None and cancel.wait(0.5):
                    self.stop()
                    raise LocalIrodoriInstallCancelled()
                if cancel is None:
                    time.sleep(0.5)
                if _irodori_ready(self.host, self.port):
                    return
                if self._process.poll() is not None:
                    try:
                        detail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                    except OSError:
                        detail = ""
                    raise RuntimeError(
                        detail.strip() or tr("本機 Irodori-TTS 服務啟動失敗。")
                    )
            self.stop()
            raise RuntimeError(tr("本機 Irodori-TTS 模型載入逾時，請查看執行記錄。"))

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            return
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
