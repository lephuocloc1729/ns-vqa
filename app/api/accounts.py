"""Site accounts: one login per tester for the web server's password prompt (docs/plans/admin-page.md).

The web server (nginx) checks the site's password itself, from a password file. The API keeps the
accounts in its database and writes that file into a volume both containers share. It holds the
shared account from .env (BASIC_AUTH_USER) and every enabled tester account. nginx reads the file
on each request, so a new, reset or disabled account takes effect at once, with no restart.

Passwords are stored and written only as apr1 hashes, the format nginx checks by itself
(the same one `openssl passwd -apr1` makes). Generated passwords are random (about 71 bits),
shown once, and never stored in plain text.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Iterable

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,31}$")
# no 0/o, 1/l/i: passwords are read out and typed by hand
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_APR1_CHARS = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def new_password(length: int = 12) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _to64(v: int, n: int) -> str:
    out = []
    for _ in range(n):
        out.append(_APR1_CHARS[v & 0x3F])
        v >>= 6
    return "".join(out)


def apr1(password: str, salt: str | None = None) -> str:
    """The Apache MD5 ("$apr1$") hash, as `openssl passwd -apr1 -salt <salt>` makes it."""
    pw = password.encode("utf-8")
    salt = (salt or "".join(secrets.choice(_APR1_CHARS) for _ in range(8)))[:8]
    s = salt.encode("ascii")
    magic = b"$apr1$"
    final = hashlib.md5(pw + s + pw).digest()
    ctx = pw + magic + s
    for i in range(len(pw), 0, -16):
        ctx += final[:min(16, i)]
    i = len(pw)
    while i:
        ctx += b"\x00" if i & 1 else pw[:1]
        i >>= 1
    final = hashlib.md5(ctx).digest()
    for i in range(1000):
        c = pw if i & 1 else final
        if i % 3:
            c += s
        if i % 7:
            c += pw
        c += final if i & 1 else pw
        final = hashlib.md5(c).digest()
    f = final
    parts = [
        _to64((f[0] << 16) | (f[6] << 8) | f[12], 4),
        _to64((f[1] << 16) | (f[7] << 8) | f[13], 4),
        _to64((f[2] << 16) | (f[8] << 8) | f[14], 4),
        _to64((f[3] << 16) | (f[9] << 8) | f[15], 4),
        _to64((f[4] << 16) | (f[10] << 8) | f[5], 4),
        _to64(f[11], 2),
    ]
    return f"$apr1${salt}${''.join(parts)}"


def check_apr1(password: str, hashed: str) -> bool:
    parts = hashed.split("$")
    if len(parts) != 4 or parts[1] != "apr1":
        return False
    return secrets.compare_digest(apr1(password, parts[2]), hashed)


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


def htpasswd_text(entries: Iterable[tuple[str, str]]) -> str:
    """entries: (name, apr1 hash). Names are checked again here: a bad one never reaches nginx."""
    lines = []
    for name, hashed in entries:
        if ":" in name or "\n" in name or "\n" in hashed or not hashed.startswith("$apr1$"):
            raise ValueError(f"bad password-file entry for {name!r}")
        lines.append(f"{name}:{hashed}")
    return "\n".join(lines) + ("\n" if lines else "")


def write_htpasswd(path: Path, entries: Iterable[tuple[str, str]]) -> None:
    """Replace the file in one step (write a temporary file next to it, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = htpasswd_text(entries)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".users-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)          # nginx's workers run as another user and must read it
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
