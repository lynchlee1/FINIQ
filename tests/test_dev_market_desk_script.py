from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def _write_executable(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def test_dev_market_desk_stops_frontend_when_backend_exits_cleanly(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    script_path = tmp_path / "scripts" / "dev-market-desk.sh"
    script_path.parent.mkdir(parents=True)
    shutil.copy2(project_root / "scripts" / "dev-market-desk.sh", script_path)
    (tmp_path / "frontend").mkdir()
    fake_bin = tmp_path / "fake-bin"

    _write_executable(
        tmp_path / ".venv" / "bin" / "python",
        """#!/usr/bin/env bash
touch "$FAKE_ROOT/backend-ready"
sleep 0.3
exit 0
""",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
test -f "$FAKE_ROOT/backend-ready"
""",
    )
    _write_executable(
        fake_bin / "npm",
        """#!/usr/bin/env bash
touch "$FAKE_ROOT/frontend-started"
trap 'touch "$FAKE_ROOT/frontend-terminated"; exit 0' TERM INT
for _index in $(seq 1 40); do
  sleep 0.05
done
touch "$FAKE_ROOT/frontend-expired"
""",
    )
    environment = {
        **os.environ,
        "FAKE_ROOT": str(tmp_path),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    }

    completed = subprocess.run(
        ["bash", str(script_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "frontend-started").is_file()
    assert (tmp_path / "frontend-terminated").is_file()
    assert not (tmp_path / "frontend-expired").exists()
