"""ShinyColorsPet desktop entry point."""

from __future__ import annotations

import sys


def _restore_worker_streams() -> None:
    """Attach cx_Freeze's GUI process to the pipes supplied by QProcess."""
    if sys.stdin is None:
        sys.stdin = open(0, encoding="utf-8", closefd=False)  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = open(1, "w", encoding="utf-8", closefd=False)  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(2, "w", encoding="utf-8", closefd=False)  # noqa: SIM115


def main() -> int:
    """Dispatch the public UI or a packaged internal pet worker."""
    if len(sys.argv) > 1 and sys.argv[1] == "--internal-worker":
        del sys.argv[1]
        _restore_worker_streams()
        from shiny_pet.process.worker import main as worker_main

        return worker_main()

    from shiny_pet.app.companion_app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
