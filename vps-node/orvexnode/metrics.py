"""Resource sampling and Proxmox-compatible RRD history.

The collector samples every instance (Incus state API) and the host (/proc)
every few seconds. It keeps the latest values for /status/current and
averages them into five round-robin archives, matching what Proxmox returns
from /rrddata for the hour, day, week, month and year timeframes.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from .incus import IncusClient, IncusError
from .util import LOG, parse_int, parse_size, read_json, write_json_atomic

TIMEFRAMES: Dict[str, int] = {"hour": 60, "day": 1800, "week": 10800, "month": 43200, "year": 604800}
ROWS = 70

_METRIC_RE = re.compile(r'^(incus_disk_(?:read|written)_bytes_total)\{([^}]*)\}\s+([0-9.eE+-]+)')
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


class Rrd:
    """Five averaging archives (slot -> [count, sums]) with ROWS rows each."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.archives: Dict[str, "OrderedDict[int, List[Any]]"] = {tf: OrderedDict() for tf in TIMEFRAMES}
        for tf, rows in (data or {}).items():
            if tf in self.archives and isinstance(rows, list):
                for row in rows:
                    try:
                        self.archives[tf][int(row[0])] = [int(row[1]), dict(row[2])]
                    except (TypeError, ValueError, IndexError):
                        continue

    def add(self, ts: float, values: Dict[str, float]) -> None:
        for tf, step in TIMEFRAMES.items():
            slot = int(ts // step) * step
            archive = self.archives[tf]
            row = archive.get(slot)
            if row is None:
                row = archive[slot] = [0, {}]
                while len(archive) > ROWS + 1:
                    archive.popitem(last=False)
            row[0] += 1
            sums = row[1]
            for key, value in values.items():
                if value is None:
                    continue
                sums[key] = sums.get(key, 0.0) + float(value)

    def points(self, timeframe: str, now: Optional[float] = None) -> List[Dict[str, Any]]:
        step = TIMEFRAMES.get(timeframe, 60)
        archive = self.archives.get(timeframe) or OrderedDict()
        end = int((now or time.time()) // step) * step
        out = []
        for slot in range(end - (ROWS - 1) * step, end + step, step):
            point: Dict[str, Any] = {"time": slot}
            row = archive.get(slot)
            if row and row[0]:
                for key, total in row[1].items():
                    point[key] = total / row[0]
            out.append(point)
        return out

    def to_json(self) -> Dict[str, Any]:
        return {tf: [[slot, row[0], row[1]] for slot, row in archive.items()] for tf, archive in self.archives.items()}


def _read_proc_stat() -> Tuple[float, float, float]:
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        fields = [float(x) for x in handle.readline().split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
    iowait = fields[4] if len(fields) > 4 else 0.0
    return sum(fields), idle, iowait


def _read_meminfo() -> Dict[str, int]:
    info: Dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts:
                info[key] = int(parts[0]) * 1024
    return info


def _read_netdev(interface: str) -> Tuple[int, int]:
    with open("/proc/net/dev", "r", encoding="utf-8") as handle:
        for line in handle.readlines()[2:]:
            name, _, data = line.partition(":")
            if name.strip() == interface:
                fields = data.split()
                return int(fields[0]), int(fields[8])
    return 0, 0


class MetricsCollector(threading.Thread):
    def __init__(self, cfg: Any, incus: IncusClient, state_dir: str, uplink: str = ""):
        super().__init__(name="metrics", daemon=True)
        self.cfg = cfg
        self.incus = incus
        self.interval = max(2, int(cfg.get("metrics_interval", 10)))
        self.dir = os.path.join(state_dir, "rrd")
        self.uplink = uplink
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._prev: Dict[int, Dict[str, float]] = {}
        self._current: Dict[int, Dict[str, Any]] = {}
        self._rrds: Dict[Any, Rrd] = {}
        self._node_prev: Optional[Dict[str, float]] = None
        self._node_current: Dict[str, Any] = {}
        self._last_persist = time.time()
        os.makedirs(self.dir, exist_ok=True)

    # ----------------------------------------------------------- storage
    def _rrd(self, key: Any) -> Rrd:
        rrd = self._rrds.get(key)
        if rrd is None:
            rrd = Rrd(read_json(os.path.join(self.dir, "%s.json" % key), None))
            self._rrds[key] = rrd
        return rrd

    def persist(self) -> None:
        with self._lock:
            items = [(key, rrd.to_json()) for key, rrd in self._rrds.items()]
        for key, data in items:
            try:
                write_json_atomic(os.path.join(self.dir, "%s.json" % key), data, mode=0o644)
            except OSError as exc:
                LOG.warning("could not persist RRD %s: %s", key, exc)
        self._last_persist = time.time()

    def forget(self, vmid: int) -> None:
        with self._lock:
            self._rrds.pop(vmid, None)
            self._current.pop(vmid, None)
            self._prev.pop(vmid, None)
        try:
            os.unlink(os.path.join(self.dir, "%d.json" % vmid))
        except OSError:
            pass

    # ------------------------------------------------------------- query
    def current(self, vmid: int) -> Dict[str, Any]:
        with self._lock:
            return dict(self._current.get(vmid, {}))

    def points(self, vmid: int, timeframe: str) -> List[Dict[str, Any]]:
        with self._lock:
            return self._rrd(vmid).points(timeframe)

    def node_current(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._node_current)

    def node_points(self, timeframe: str) -> List[Dict[str, Any]]:
        with self._lock:
            return self._rrd("node").points(timeframe)

    # ------------------------------------------------------------ sample
    def disk_io(self) -> Dict[str, Tuple[int, int]]:
        totals: Dict[str, List[int]] = {}
        try:
            text = self.incus.metrics_text()
        except IncusError as exc:
            LOG.debug("metrics endpoint unavailable: %s", exc)
            return {}
        for line in text.splitlines():
            match = _METRIC_RE.match(line)
            if not match:
                continue
            labels = dict(_LABEL_RE.findall(match.group(2)))
            name = labels.get("name")
            if not name:
                continue
            entry = totals.setdefault(name, [0, 0])
            value = int(float(match.group(3)))
            if match.group(1).endswith("read_bytes_total"):
                entry[0] += value
            else:
                entry[1] += value
        return {k: (v[0], v[1]) for k, v in totals.items()}

    def sample_instances(self, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        instances = self.incus.instances(recursion=2)
        io = self.disk_io()
        host_cpus = os.cpu_count() or 1
        seen = set()
        for inst in instances:
            config = inst.get("config") or {}
            vmid = parse_int(config.get("user.orvex.vmid"))
            if not vmid:
                continue
            seen.add(vmid)
            state = inst.get("state") or {}
            running = (inst.get("status") or state.get("status")) in ("Running", "Frozen")
            maxcpu = parse_int(config.get("limits.cpu"), host_cpus) or host_cpus
            maxmem = parse_size(config.get("limits.memory"), "") or 0
            root = (inst.get("devices") or {}).get("root") or {}
            maxdisk = parse_size(root.get("size"), "") or 0
            cpu_ns = float(((state.get("cpu") or {}).get("usage")) or 0)
            net = state.get("network") or {}
            netin = sum(int((v.get("counters") or {}).get("bytes_received", 0)) for k, v in net.items() if k != "lo")
            netout = sum(int((v.get("counters") or {}).get("bytes_sent", 0)) for k, v in net.items() if k != "lo")
            dread, dwrite = io.get(inst.get("name", ""), (0, 0))
            mem = int(((state.get("memory") or {}).get("usage")) or 0)
            disk = int((((state.get("disk") or {}).get("root") or {}).get("usage")) or 0)
            with self._lock:
                prev = self._prev.get(vmid)
                rates = {"cpu": 0.0, "netin": 0.0, "netout": 0.0, "diskread": 0.0, "diskwrite": 0.0}
                if prev and running and ts > prev["ts"]:
                    elapsed = ts - prev["ts"]
                    rates["cpu"] = max(0.0, min(1.0, (cpu_ns - prev["cpu_ns"]) / (elapsed * 1e9 * maxcpu)))
                    for key, value in (("netin", netin), ("netout", netout), ("diskread", dread), ("diskwrite", dwrite)):
                        delta = value - prev[key]
                        rates[key] = delta / elapsed if delta >= 0 else 0.0
                self._prev[vmid] = {"ts": ts, "cpu_ns": cpu_ns, "netin": netin, "netout": netout, "diskread": dread, "diskwrite": dwrite}
                self._current[vmid] = {
                    "cpu": rates["cpu"], "mem": mem, "disk": disk, "netin": netin, "netout": netout,
                    "diskread": dread, "diskwrite": dwrite,
                }
                point = {"maxcpu": maxcpu, "maxmem": maxmem, "maxdisk": maxdisk, "disk": disk}
                if running:
                    point.update({"cpu": rates["cpu"], "mem": mem, "netin": rates["netin"], "netout": rates["netout"],
                                  "diskread": rates["diskread"], "diskwrite": rates["diskwrite"]})
                self._rrd(vmid).add(ts, point)
        with self._lock:
            for vmid in [v for v in self._current if v not in seen]:
                self._current.pop(vmid, None)
                self._prev.pop(vmid, None)

    def sample_node(self, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        try:
            total, idle, iowait = _read_proc_stat()
            mem = _read_meminfo()
            netin, netout = _read_netdev(self.uplink) if self.uplink else (0, 0)
            load1 = os.getloadavg()[0]
            vfs = os.statvfs("/")
        except OSError as exc:
            LOG.debug("node sample failed: %s", exc)
            return
        roottotal = vfs.f_blocks * vfs.f_frsize
        rootused = (vfs.f_blocks - vfs.f_bfree) * vfs.f_frsize
        memtotal = mem.get("MemTotal", 0)
        memused = memtotal - mem.get("MemAvailable", mem.get("MemFree", 0))
        swaptotal = mem.get("SwapTotal", 0)
        swapused = swaptotal - mem.get("SwapFree", 0)
        with self._lock:
            prev = self._node_prev
            cpu = io_frac = 0.0
            rin = rout = 0.0
            if prev and total > prev["total"]:
                span = total - prev["total"]
                cpu = max(0.0, min(1.0, 1.0 - (idle - prev["idle"]) / span))
                io_frac = max(0.0, min(1.0, (iowait - prev["iowait"]) / span))
                elapsed = max(0.001, ts - prev["ts"])
                rin = max(0.0, (netin - prev["netin"]) / elapsed)
                rout = max(0.0, (netout - prev["netout"]) / elapsed)
            self._node_prev = {"ts": ts, "total": total, "idle": idle, "iowait": iowait, "netin": netin, "netout": netout}
            self._node_current = {
                "cpu": cpu, "maxcpu": os.cpu_count() or 1, "mem": memused, "maxmem": memtotal,
                "disk": rootused, "maxdisk": roottotal, "swapused": swapused, "swaptotal": swaptotal,
                "loadavg": load1, "iowait": io_frac,
            }
            self._rrd("node").add(ts, {
                "cpu": cpu, "maxcpu": os.cpu_count() or 1, "iowait": io_frac, "loadavg": load1,
                "memused": memused, "memtotal": memtotal, "swapused": swapused, "swaptotal": swaptotal,
                "rootused": rootused, "roottotal": roottotal, "netin": rin, "netout": rout,
            })

    def run(self) -> None:  # pragma: no cover - timing loop
        while not self._stop.is_set():
            started = time.time()
            try:
                self.sample_node(started)
                self.sample_instances(started)
            except IncusError as exc:
                LOG.warning("metrics sample failed: %s", exc)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                LOG.exception("unexpected metrics error: %s", exc)
            if time.time() - self._last_persist >= 60:
                self.persist()
            self._stop.wait(max(0.5, self.interval - (time.time() - started)))
        self.persist()

    def stop(self) -> None:
        self._stop.set()
