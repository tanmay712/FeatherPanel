"""OrveX VPS Node.

A node daemon that lets OrveX Panel run KVM virtual machines and LXC
containers on any Debian/Ubuntu server, without Proxmox.

The daemon speaks the subset of the Proxmox VE HTTP API that the panel
(PHP backend and Rust async runner) already uses, and translates every call
to Incus, which manages both containers (LXC) and virtual machines (QEMU/KVM)
through one API. Adding a node to the panel therefore works exactly like
adding a Proxmox node.
"""

__version__ = "1.0.0"

# Version string reported on /api2/json/version. The panel only displays it.
PVE_COMPAT_VERSION = "8.2.4"
