"""Managed local faster-whisper service used by the desktop application.

The runtime is deliberately isolated from the GUI Python environment.  This keeps
large CUDA/ctranslate2 dependencies out of application startup while still making
the local recognizer an application-managed feature.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

LOCAL_ASR_HOST = "127.0.0.1"
LOCAL_ASR_PORT = 8178
LOCAL_ASR_MODEL = "Systran/faster-whisper-large-v3"
LOCAL_ASR_API_URL = f"http://{LOCAL_ASR_HOST}:{LOCAL_ASR_PORT}/v1/audio/transcriptions"
_RUNTIME_VERSION = "1"

_REQUIREMENTS = """fastapi>=0.115,<1
uvicorn>=0.30,<1
python-multipart>=0.0.9,<1
faster-whisper>=1.1,<2
"""

_SERVER = r'''import os
import tempfile
import threading
import time
import traceback

import ctranslate2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import WhisperModel


MODEL_NAME = os.environ.get("ASR_MODEL", "Systran/faster-whisper-large-v3")
HOST = os.environ.get("ASR_HOST", "127.0.0.1")
PORT = int(os.environ.get("ASR_PORT", "8178"))
OWNER_PID = int(os.environ.get("ASR_OWNER_PID", "0") or "0")
REQUESTED_DEVICE = os.environ.get("ASR_DEVICE", "auto").strip().lower()
if REQUESTED_DEVICE == "auto":
    DEVICE = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
else:
    DEVICE = REQUESTED_DEVICE
COMPUTE_TYPE = os.environ.get(
    "ASR_COMPUTE_TYPE", "float16" if DEVICE == "cuda" else "int8"
)

app = FastAPI()
_model = None
_model_error = ""
_model_lock = threading.Lock()


def _owner_alive():
    if OWNER_PID <= 0:
        return True
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, OWNER_PID)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(OWNER_PID, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def _watch_owner():
    while _owner_alive():
        time.sleep(1)
    os._exit(0)


def _load_model():
    global _model, _model_error
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
                _model_error = ""
            except Exception as exc:
                _model_error = str(exc)
                raise
    return _model


if OWNER_PID > 0:
    threading.Thread(target=_watch_owner, name="shiny-asr-owner", daemon=True).start()


@app.on_event("startup")
def warm_model():
    print(
        f"Loading {MODEL_NAME} with device={DEVICE}, compute_type={COMPUTE_TYPE}",
        flush=True,
    )
    def run():
        try:
            _load_model()
        except Exception:
            traceback.print_exc()
    threading.Thread(target=run, name="shiny-asr-model", daemon=True).start()


@app.get("/health")
def health():
    return {
        "ok": not bool(_model_error),
        "ready": _model is not None,
        "error": _model_error,
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
    }


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_name: str = Form("", alias="model"),
    language: str = Form("", alias="language"),
):
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as stream:
        stream.write(await file.read())
        path = stream.name
    try:
        try:
            model = _load_model()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"Whisper model unavailable: {exc}"
            ) from exc
        segments, _info = model.transcribe(path, language=language or None, vad_filter=True)
        return {"text": "".join(segment.text for segment in segments).strip()}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
'''


class LocalASRInstallCancelled(RuntimeError):
    """Raised when the user cancels local runtime installation."""


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _python_venv_command() -> list[str]:
    """Return a usable interpreter command, avoiding a frozen GUI executable."""
    if not getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        if executable.exists() and not _is_conda_python(executable):
            return [str(executable)]
    if sys.platform == "win32":
        candidates: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidates.extend(
                Path(local_app_data).glob("Programs/Python/Python*/python.exe")
            )
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable, "").strip()
            if root:
                candidates.extend(Path(root).glob("Python*/python.exe"))
        for candidate in sorted(candidates, reverse=True):
            if candidate.is_file() and not _is_conda_python(candidate):
                return [str(candidate)]
    for name in ("python3", "python"):
        discovered = shutil.which(name)
        if discovered and not _is_conda_python(Path(discovered)):
            return [discovered]
    raise RuntimeError(
        "找不到可建立語音辨識環境的標準 Python 3.10 以上版本。"
        "Anaconda/Miniconda 因原生 DLL 衝突不支援，請從 python.org 安裝 Python。"
    )


def _is_conda_python(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return any(part in normalized for part in ("/anaconda", "/miniconda", "/conda/"))


class LocalWhisperASRServer:
    """Own the isolated runtime, server process, and application shutdown cleanup."""

    def __init__(self, runtime_dir: Path, *, port: int = LOCAL_ASR_PORT) -> None:
        self.runtime_dir = runtime_dir
        self.host = LOCAL_ASR_HOST
        self.port = port
        self._process: subprocess.Popen[bytes] | None = None
        self._active_force_cpu: bool | None = None
        self._lock = threading.RLock()

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1/audio/transcriptions"

    @property
    def python(self) -> Path:
        if sys.platform == "win32":
            return self.runtime_dir / ".venv" / "Scripts" / "python.exe"
        return self.runtime_dir / ".venv" / "bin" / "python"

    @property
    def installed(self) -> bool:
        marker = self.runtime_dir / ".install-complete"
        try:
            version = marker.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        return (
            version == _RUNTIME_VERSION
            and self.python.is_file()
            and (self.runtime_dir / "server.py").is_file()
            and not self._venv_uses_conda()
        )

    def _venv_uses_conda(self) -> bool:
        config = self.runtime_dir / ".venv" / "pyvenv.cfg"
        try:
            text = config.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return _is_conda_python(Path(text))

    def _remove_unsafe_venv(self) -> None:
        venv = self.runtime_dir / ".venv"
        if not venv.exists() or not self._venv_uses_conda():
            return
        runtime = self.runtime_dir.resolve()
        resolved = venv.resolve()
        if resolved.parent != runtime or resolved.name != ".venv":
            raise RuntimeError(f"拒絕移除非預期的語音辨識環境：{resolved}")
        shutil.rmtree(resolved)

    def _write_runtime(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "requirements.txt").write_text(_REQUIREMENTS, encoding="utf-8")
        (self.runtime_dir / "server.py").write_text(_SERVER, encoding="utf-8")

    @staticmethod
    def _run(
        command: list[str], cwd: Path, cancel: threading.Event,
        progress: Callable[[str], None],
    ) -> None:
        if cancel.is_set():
            raise LocalASRInstallCancelled()
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(
            command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, startupinfo=startupinfo, creationflags=creationflags,
        )
        output = b""
        while True:
            if cancel.is_set():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise LocalASRInstallCancelled()
            try:
                output, _stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
        decoded = output.decode(errors="replace").strip()
        if process.returncode:
            raise RuntimeError(decoded[-2000:] or f"安裝指令失敗（{process.returncode}）")
        if decoded:
            progress(decoded[-500:])

    def install(
        self, cancel: threading.Event, progress: Callable[[str], None] | None = None,
    ) -> str:
        report = progress or (lambda _message: None)
        report("正在準備 Whisper 本機執行環境…")
        (self.runtime_dir / ".install-complete").unlink(missing_ok=True)
        if self._venv_uses_conda():
            report("偵測到會造成原生 DLL 崩潰的 Anaconda 環境，正在安全重建…")
            self._remove_unsafe_venv()
        self._write_runtime()
        if not self.python.exists():
            report("正在建立獨立 Python 環境…")
            self._run(
                [*_python_venv_command(), "-m", "venv", str(self.runtime_dir / ".venv")],
                self.runtime_dir, cancel, report,
            )
        report("正在安裝 faster-whisper；首次安裝需要下載必要元件…")
        self._run(
            [str(self.python), "-m", "pip", "install", "--disable-pip-version-check", "-r",
             "requirements.txt"],
            self.runtime_dir, cancel, report,
        )
        (self.runtime_dir / ".install-complete").write_text(
            _RUNTIME_VERSION + "\n", encoding="utf-8"
        )
        report("正在啟動 whisper-large-v3；模型會在背景下載及載入…")
        self.ensure_running(cancel)
        return self.api_url

    def ensure_running(
        self, cancel: threading.Event | None = None, *, force_cpu: bool = False,
    ) -> None:
        if force_cpu and self._active_force_cpu is False:
            self.stop()
        if _port_open(self.host, self.port):
            return
        if not self.installed:
            detail = (
                "目前的 ASR runtime 來自不相容的 Anaconda，請回到「語音辨識」重新執行一鍵安裝。"
                if self._venv_uses_conda()
                else "本機 Whisper 尚未安裝，請先到「語音辨識」設定執行一鍵安裝。"
            )
            raise RuntimeError(detail)
        # Refresh the small managed server on every application update without reinstalling
        # the isolated third-party dependencies or model cache.
        self._write_runtime()
        with self._lock:
            if _port_open(self.host, self.port):
                return
            log_path = self.runtime_dir / "server.log"
            env = os.environ.copy()
            env.update({
                "ASR_MODEL": LOCAL_ASR_MODEL,
                "ASR_DEVICE": "cpu" if force_cpu else "auto",
                "ASR_HOST": self.host,
                "ASR_PORT": str(self.port),
                "ASR_OWNER_PID": str(os.getpid()),
            })
            if force_cpu:
                env["ASR_COMPUTE_TYPE"] = "int8"
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            with log_path.open("ab") as log:
                self._process = subprocess.Popen(
                    [str(self.python), str(self.runtime_dir / "server.py")],
                    cwd=str(self.runtime_dir), env=env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, creationflags=creationflags,
                )
                self._active_force_cpu = force_cpu
            for _ in range(80):
                if cancel is not None and cancel.wait(0.25):
                    self.stop()
                    raise LocalASRInstallCancelled()
                if cancel is None:
                    time.sleep(0.25)
                if _port_open(self.host, self.port):
                    return
                if self._process.poll() is not None:
                    try:
                        detail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
                    except OSError:
                        detail = ""
                    raise RuntimeError(detail.strip() or "本機 Whisper 服務啟動失敗。")
            raise RuntimeError("本機 Whisper 服務啟動逾時，請查看語音辨識執行記錄。")

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._active_force_cpu = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
