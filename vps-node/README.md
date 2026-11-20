# ⚡ OrveX VPS Node

The panel's own VPS node system: turn any Debian or Ubuntu server into a node for **OrveX Panel**, with KVM
virtual machines and LXC containers, dedicated and shared IPv4, and no Proxmox needed.

Create the node in the panel (**Admin → VDS Nodes → Create → OrveX Node**) and run the command it shows on the
server. It looks like this, and the node connects itself:

```bash
curl -fsSL https://raw.githubusercontent.com/tanmay712/FeatherPanel/develop/install.sh | sudo bash -s -- vps-node --panel https://panel.example.com --token orvx_… -y
```

## How it works

```
OrveX Panel ──HTTPS (Proxmox VE API subset)──▶ orvex-node (this agent, port 8006)
 (PHP + Rust runner)                                │
                                                    ▼  unix socket
                                                  Incus ──▶ KVM VMs (QEMU) + LXC containers
```

The panel already manages Proxmox VE through its HTTP API. `orvex-node` implements the part of that API the
panel and its async runner use (nodes, storage, bridges, template clones, config, power, resize, status,
RRD stats, snapshots, vzdump backups and restores, tasks, VNC console). It translates every call into
[Incus](https://linuxcontainers.org/incus/), which runs containers and virtual machines through one API.
Every VDS screen therefore works on OrveX nodes. In the panel they are their own node type, which connects
itself (see below) and hides the Proxmox-only settings.

* **Guests** are Incus instances named `vps<VMID>`. The Proxmox-style config the panel writes
  (`memory`, `cores`, `net0`, `ipconfig0`, `ciuser`, `cipassword`, `sshkeys`, ...) is stored on the instance
  (`user.orvex.pve`) and turned into Incus limits, NIC devices and **cloud-init** documents.
* **Templates** are virtual: each template VMID maps to an image from `images.linuxcontainers.org`
  (cloud variants, with cloud-init). Images are cached locally after the first use or by `orvex-node cache-templates`.
* **Config changes on running guests** that Incus cannot apply live are kept and applied on the next start or
  reboot, like Proxmox pending changes.
* The agent is **Python 3 standard library only** (3.7+): no pip, no virtualenv.

## Connecting to the panel

```
Panel: Admin > VDS Nodes > Create > OrveX Node  ->  one-time install command (token valid 24 h)
Server: install.sh vps-node --panel URL --token T  ->  installs everything, then `orvex-node register`
        POST {panel}/api/remote/orvex/register  ->  panel saves the node, adds templates + shared IPv4 pool,
                                                   checks it can reach https://<node>:8006, token is used up
```

`orvex-node register --panel URL --token TOKEN [--address HOST] [--insecure]` sends the panel how to reach the
node (address, port 8006, API token) and what it offers: templates, storage pool, shared-IPv4 network, KVM support
and host details. The panel then:

* fills in the node's connection details (the admin never types a token or secret),
* adds the templates it does not know yet (KVM templates stay inactive when the server has no `/dev/kvm`),
* adds the shared-IPv4 subnet to the node's IP pool (`10.77.0.2-10.77.0.254` by default), unless the pool already
  has addresses from that subnet,
* checks that it can reach the node API and reports the result to the installer.

Tokens work once and expire after 24 hours. To connect again after reinstalling the server, changing its address
or running `orvex-node rotate-token`, open the node in the panel → *Connect* → **Re-pair node** (or **New command**)
and run the `orvex-node register` command it shows. The address defaults to `public_ipv4`; pass `--address` to use
a host name instead. `--insecure` skips the check of the panel's TLS certificate. The panel URL and node ID are
saved in `/etc/orvex-node/panel.json`.

The panel must reach TCP port `8006` on the node. *Sync from node* on the node page re-reads the node report
(`GET /api2/json/nodes/{node}/orvex/info`) and adds new templates.

## Networking

| Panel bridge | Mode | Use it for | Guest configuration |
| --- | --- | --- | --- |
| `orvexpub0` | routed NIC on the uplink | dedicated IPv4 routed to the server (most providers) | `<ip>/32`, gateway `169.254.0.1` |
| `orvexnat0` | NAT bridge | **shared IPv4**: private `10.77.0.0/24` | `<ip>/24`, gateway `10.77.0.1` |
| any host bridge (`vmbr0`, `br0`) | bridged | dedicated IPv4 with the provider's gateway | IP, CIDR and gateway from the panel |

If the panel sends an unknown bridge name (for example the default `vmbr0` on a node without that bridge), the
address decides: private addresses in the NAT subnet use NAT, everything else is routed.

**Shared IPv4 forwards.** For a NAT guest with private IP `10.77.0.N` the node forwards, on its public IPv4:

* `22000 + N` (TCP) → port 22 of the guest (SSH)
* `30000 + N × 20` … `+19` (TCP and UDP) → the same ports inside the guest

The forwards are Incus network forwards on `orvexnat0` and are kept in sync automatically: on start, on config
changes and on delete, including reinstalls where the old and new guest briefly share the IP. Users see the
SSH endpoint and the port range in the panel (overview and network pages).

## Access for customers

* **Password**: KVM guests get the cloud-init user (`ciuser`) with the chosen password. Containers get a root
  password, registered by the panel before the clone. *Change password* in the panel applies instantly with
  `chpasswd` inside the running guest (`incus exec`), and is also stored for cloud-init so it survives restarts.
* **SSH**: password authentication is enabled with a drop-in (`/etc/ssh/sshd_config.d/01-orvex.conf`), and
  `openssh-server` is installed in containers.
* **Console**: KVM guests get a VNC display on `127.0.0.1` (QEMU `-vnc`), proxied over a ticketed websocket
  exactly like Proxmox. If QEMU refuses the option, the guest starts without a graphical console. Containers
  use SSH. With the self-signed node certificate, enable **Admin → Settings → Proxy VNC via panel**.

## Configuration

`/etc/orvex-node/config.json` (created by the installer; restart the agent after editing it):

| Key | Default | Meaning |
| --- | --- | --- |
| `node_name` | hostname | Node name shown in the panel |
| `port` | `8006` | API port (HTTPS) |
| `api_user` / `api_token_id` / `api_token_secret` | `orvex@orvex` / `panel` / random | Token for the panel. The `@orvex` realm tells the panel this is an OrveX node |
| `public_ipv4` | detected | Listen address for NAT forwards and SSH host for NAT guests |
| `uplink_interface` | default route | Parent interface of routed NICs |
| `storage_pool` | `default` | Incus storage pool for guests |
| `nat.subnet` / `nat.gateway` | `10.77.0.0/24` / `10.77.0.1` | Shared IPv4 network (`orvexnat0`) |
| `nat.listen_address` | auto | Address the forwards listen on. Auto uses `public_ipv4` when it is assigned to the server, otherwise the local address (for 1:1 NAT clouds such as AWS, GCP or Oracle) |
| `nat.ssh_port_base` | `22000` | SSH forward = base + N |
| `nat.port_range_base` / `nat.port_range_size` | `30000` / `20` | Service ports = base + N × size … + size − 1 |
| `nameservers` | `1.1.1.1 8.8.8.8` | Default DNS for guests |
| `vnc_enabled` / `vnc_display_base` | `true` / `100` | Graphical console for KVM guests |
| `backup_dir` | `/var/lib/orvex-node/backups` | vzdump-style archives (storage `backups` in the panel) |
| `templates_file` | `/etc/orvex-node/templates.json` | Template catalog |

**Templates** (`/etc/orvex-node/templates.json`): add or remove entries freely. Each entry needs a unique
`vmid`, a `type` (`qemu` or `lxc`) and an `image` alias from `images.linuxcontainers.org` (use the `/cloud`
variants so cloud-init is available).

```json
{ "vmid": 9007, "name": "fedora-41-kvm", "type": "qemu", "image": "fedora/41/cloud",
  "description": "Fedora 41 (KVM)", "default_user": "fedora", "disk_gb": 10 }
```

## Commands

| Command | Does |
| --- | --- |
| `orvex-node register --panel URL --token T` | Connect the node to the panel with the token from the panel |
| `orvex-node info` | Panel connection, plus the values for adding the node by hand, bridges, IP pool and templates |
| `orvex-node status` | Guests with type, status, IP, network mode and SSH endpoint |
| `orvex-node templates` | Template catalog and cache state |
| `orvex-node cache-templates [name\|vmid ...]` | Pre-download images (all templates by default) |
| `orvex-node doctor` | Check Incus, KVM, forwarding, storage pool, NAT bridge, uplink, TLS and token |
| `orvex-node rotate-token` | New API secret (then re-pair the node from the panel) |
| `orvex node-update` | Update the agent from GitHub |

Logs: `journalctl -u orvex-node -f`. Guests can also be inspected with plain Incus (`incus list`, `incus info vps5000`).

## Not available yet

The Proxmox firewall, the ISO library and rescue ISO, cluster migration and the container terminal proxy. The
panel hides these features for OrveX nodes, and the API answers `501` for them.

## Development

```bash
cd vps-node
python3 -m unittest discover -s tests -v   # end-to-end tests against a fake Incus API
PYTHONPATH=. python3 -m orvexnode --help
```

The tests drive the agent over HTTP the way the PHP backend (form bodies) and the Rust runner (JSON bodies)
do: clones, runner and PHP config flows, NAT forwards, password changes, snapshots, backups that the runner can
parse, RRD data, the VNC websocket bridge, TLS and the fallback paths.
