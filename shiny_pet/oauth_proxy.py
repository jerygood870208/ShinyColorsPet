"""On-demand manager for the unofficial openai-oauth loopback proxy."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from shiny_pet.ai.llm import discover_openai_models

NODE_VERSION = "22.23.2"
OPENAI_OAUTH_VERSION = "2.0.0"
NODE_ARCHIVE = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_RELEASE = f"https://nodejs.org/download/release/v{NODE_VERSION}"
PROXY_URL = "http://127.0.0.1:10531/v1"


class OpenAIOAuthProxyManager:
    """Provision pinned prerequisites and operate the proxy without reading OAuth credentials."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.node_root = self.root / f"node-v{NODE_VERSION}-win-x64"

    @property
    def node(self) -> Path:
        return self.node_root / "node.exe"

    @property
    def npx_cli(self) -> Path:
        return self.node_root / "node_modules" / "npm" / "bin" / "npx-cli.js"

    @staticmethod
    def _download(url: str, destination: Path, maximum: int) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "ShinyColorsPet/0.0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
            final = response.geturl()
            if not final.startswith("https://nodejs.org/"):
                raise RuntimeError("Node download redirected outside nodejs.org")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise RuntimeError("download exceeds expected size")
                out.write(chunk)

    def ensure_runtime(self, progress: Callable[[str], None] | None = None) -> None:
        if self.node.is_file() and self.npx_cli.is_file():
            return
        report = progress or (lambda _message: None)
        self.root.mkdir(parents=True, exist_ok=True)
        report("正在下載經固定版本的 Node.js 22 LTS…")
        with tempfile.TemporaryDirectory(prefix="oauth-runtime-", dir=self.root) as temporary:
            temp = Path(temporary)
            checksums = temp / "SHASUMS256.txt"
            archive = temp / NODE_ARCHIVE
            self._download(f"{NODE_RELEASE}/SHASUMS256.txt", checksums, 128 * 1024)
            expected = ""
            for line in checksums.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == NODE_ARCHIVE:
                    expected = parts[0].lower()
                    break
            if len(expected) != 64:
                raise RuntimeError("Node release checksum is missing")
            self._download(f"{NODE_RELEASE}/{NODE_ARCHIVE}", archive, 64 * 1024 * 1024)
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError("Node runtime checksum mismatch")
            report("正在解壓縮受控的本機 runtime…")
            extract_root = temp / "extract"
            extract_root.mkdir()
            resolved_extract_root = extract_root.resolve()
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    target = (extract_root / item.filename).resolve()
                    outside = (
                        resolved_extract_root not in target.parents
                        and target != resolved_extract_root
                    )
                    if outside:
                        raise RuntimeError("Node archive contains an unsafe path")
                bundle.extractall(extract_root)
            staged = extract_root / self.node_root.name
            if not (staged / "node.exe").is_file():
                raise RuntimeError("Node archive is incomplete")
            if self.node_root.exists():
                if self.root not in self.node_root.parents:
                    raise RuntimeError("refusing to replace runtime outside the managed directory")
                shutil.rmtree(self.node_root)
            shutil.move(str(staged), str(self.node_root))
        if not self.node.is_file() or not self.npx_cli.is_file():
            raise RuntimeError("Node runtime installation failed")

    def _run(self, *arguments: str, timeout: float) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = str(self.node_root) + os.pathsep + environment.get("PATH", "")
        environment["NPM_CONFIG_UPDATE_NOTIFIER"] = "false"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(
            [str(self.node), str(self.npx_cli), "--yes",
             f"openai-oauth@{OPENAI_OAUTH_VERSION}", *arguments],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=flags,
            check=False,
        )

    def ensure_and_start(self, progress: Callable[[str], None] | None = None) -> tuple[str, ...]:
        report = progress or (lambda _message: None)
        existing = discover_openai_models(PROXY_URL)
        if existing:
            return existing
        self.ensure_runtime(report)
        report("正在開啟瀏覽器登入；請只使用您本人的 ChatGPT 帳號…")
        try:
            result = self._run("--detach", timeout=360)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("openai-oauth login timed out") from exc
        if result.returncode != 0:
            detail = (result.stdout or "openai-oauth failed").strip()[-1500:]
            raise RuntimeError(detail)
        report("登入完成，正在確認本機模型…")
        for _attempt in range(30):
            models = discover_openai_models(PROXY_URL)
            if models:
                return models
            time.sleep(0.5)
        raise RuntimeError("openai-oauth 已啟動，但本機模型端點沒有回應")

    def stop(self) -> None:
        if not self.node.is_file() or not self.npx_cli.is_file():
            return
        try:
            self._run("stop", timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return
