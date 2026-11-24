"""The GPU connection, from the API's side (docs/plans/admin-page.md, PR 2).

The rag-tunnel service (docker/rag-tunnel/tunnel.sh) runs all the time and follows a target file
in a volume it shares with the API. The API only writes that file and reads the tunnel's state;
it never controls Docker, and the SSH key never leaves the tunnel container.

    target            "host port" (empty: no connection)
    state             state|target|detail; state is standby, no_key, connecting, connected or error
    server_key.pub    the server's public key, to add to the GPU provider once

    python -m app.api.gpu status | connect HOST PORT | disconnect     # VQA_GPU_DIR from the environment
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$")
STATES = ("standby", "no_key", "connecting", "connected", "error")


def check_target(host: str, port: int | str) -> tuple[str, int]:
    """A GPU's SSH address, checked: an IP address or a host name, and a port. Raises ValueError."""
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError("cổng phải là số")
    if not 1 <= port <= 65535:
        raise ValueError("cổng phải từ 1 đến 65535")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
            raise ValueError("địa chỉ máy GPU không hợp lệ")
        return str(ip), port
    if not _HOST_RE.match(host) or host.lower() == "localhost":
        raise ValueError("địa chỉ máy GPU không hợp lệ")
    return host, port


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".target-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def set_target(folder: Path, host: str, port: int) -> None:
    host, port = check_target(host, port)
    _write(Path(folder) / "target", f"{host} {port}\n")


def clear_target(folder: Path) -> None:
    _write(Path(folder) / "target", "")


def status(folder: Path) -> dict[str, Any]:
    folder = Path(folder)
    try:
        target = (folder / "target").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        target = ""
    try:
        line = (folder / "state").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        line = ""
    parts = line.split("|", 2) + ["", "", ""]
    state = parts[0] if parts[0] in STATES else ("unknown" if line else "not_running")
    try:
        key = (folder / "server_key.pub").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        key = None
    host, _, port = target.partition(" ")
    if not line:                      # the tunnel has never written a state: it is not running
        current, detail = "not_running", ""
    elif parts[1] == target:
        current, detail = state, parts[2]
    else:                             # a state about an older target: the new one is on its way
        current, detail = ("connecting" if target else "standby"), ""
    return {"target": {"host": host, "port": int(port)} if target and port.isdigit() else None,
            "state": current, "detail": detail,
            "public_key": key}


def main(argv: list[str]) -> None:
    folder = os.environ.get("VQA_GPU_DIR")
    if not folder:
        raise SystemExit("VQA_GPU_DIR is not set")
    cmd = argv[0] if argv else "status"
    if cmd == "connect" and len(argv) == 3:
        set_target(Path(folder), argv[1], int(argv[2]))
    elif cmd == "disconnect":
        clear_target(Path(folder))
    elif cmd != "status":
        raise SystemExit("usage: python -m app.api.gpu status | connect HOST PORT | disconnect")
    s = status(Path(folder))
    t = s["target"]
    print(f"{s['state']}  {t['host'] + ':' + str(t['port']) if t else '-'}  {s['detail']}".rstrip())


if __name__ == "__main__":
    main(sys.argv[1:])
