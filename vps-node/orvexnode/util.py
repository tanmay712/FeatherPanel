"""Small shared helpers (no third-party dependencies)."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Optional

LOG = logging.getLogger("orvexnode")

GIB = 1024 ** 3
MIB = 1024 ** 2

_SIZE_RE = re.compile(r"^\s*(\+)?\s*(\d+(?:\.\d+)?)\s*([KMGTP]?)(?:i?B)?\s*$", re.IGNORECASE)
_UNITS = {"": 1, "K": 1024, "M": MIB, "G": GIB, "T": 1024 ** 4, "P": 1024 ** 5}


class PveError(Exception):
    """An error that is returned to the API client Proxmox-style."""

    def __init__(self, status: int, message: str, errors: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.errors = errors


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off", ""):
        return False
    return default


def parse_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def parse_size(value: Any, default_unit: str = "") -> Optional[int]:
    """Parse a Proxmox size ("10G", "512M", "+5G", "1.5T", 1024) into bytes.

    Returns None when the value cannot be parsed. A leading "+" is ignored here;
    use :func:`is_relative_size` to detect it.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) * _UNITS.get(default_unit.upper(), 1)
    match = _SIZE_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(2))
    unit = (match.group(3) or default_unit).upper()
    return int(number * _UNITS.get(unit, 1))


def is_relative_size(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith("+")


def format_size(num_bytes: int) -> str:
    """Format bytes the way Proxmox writes disk sizes in configs (e.g. "20G")."""
    num_bytes = max(0, int(num_bytes))
    for unit, factor in (("T", 1024 ** 4), ("G", GIB), ("M", MIB), ("K", 1024)):
        if num_bytes >= factor and num_bytes % factor == 0:
            return "%d%s" % (num_bytes // factor, unit)
    if num_bytes >= GIB:
        return "%dM" % (num_bytes // MIB)
    return str(num_bytes)


def random_mac() -> str:
    """A random MAC in the Incus/LXD OUI (00:16:3e)."""
    return "00:16:3e:%02x:%02x:%02x" % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def normalize_mac(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", ":")
    if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", text):
        return text
    return None


def sanitize_hostname(value: Any, fallback: str) -> str:
    """Return a valid hostname (RFC 1123 labels, max 63 chars per label, 253 total)."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9.-]+", "-", text)
    labels = []
    for label in text.split("."):
        label = label.strip("-")[:63].strip("-")
        if label:
            labels.append(label)
    result = ".".join(labels)[:253].strip(".-")
    if not result or not re.match(r"^[a-z0-9]", result):
        return fallback
    return result


def ipv4_or_none(value: Any) -> Optional[ipaddress.IPv4Address]:
    try:
        return ipaddress.IPv4Address(str(value).strip())
    except (ipaddress.AddressValueError, ValueError):
        return None


def now() -> int:
    return int(time.time())


def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        LOG.warning("Could not read %s: %s", path, exc)
        return default


def write_json_atomic(path: str, data: Any, mode: int = 0o600) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


_HASH_LOCK = threading.Lock()


def hash_password(password: str) -> str:
    """SHA-512 crypt hash ($6$...) suitable for cloud-init and chpasswd -e.

    Uses `openssl passwd -6` (always present on supported hosts); falls back to
    the stdlib crypt module where it still exists. Raises RuntimeError if no
    hashing method is available.
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("password must be a non-empty string")
    openssl = shutil.which("openssl")
    if openssl:
        with _HASH_LOCK:
            result = subprocess.run(
                [openssl, "passwd", "-6", "-stdin"],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=15,
            )
        hashed = result.stdout.strip()
        if result.returncode == 0 and hashed.startswith("$6$"):
            return hashed
    try:  # Python < 3.13
        import crypt  # type: ignore

        return crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
    except Exception as exc:  # pragma: no cover - depends on host
        raise RuntimeError("no password hashing method available (install openssl)") from exc
