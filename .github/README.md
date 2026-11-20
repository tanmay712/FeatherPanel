<div align="center">

<img src="../frontendv2/public/branding/orvex-logo.png" alt="OrveX Panel" width="96" />

# OrveX Panel

**Open-source game server management with built-in billing, fast, secure, and built for operators.**

<sub>OrveX Panel is based on <a href="https://github.com/MythicalLTD/FeatherPanel">FeatherPanel</a> by Mythical Systems and bundles the official FeatherPanel addons out of the box.</sub>

<br /><br />

[![Frontend](https://img.shields.io/github/actions/workflow/status/tanmay712/FeatherPanel/frontend.yml?branch=develop&label=Frontend&style=for-the-badge&logo=react&logoColor=white)](https://github.com/tanmay712/FeatherPanel/actions/workflows/frontend.yml)
[![Backend](https://img.shields.io/github/actions/workflow/status/tanmay712/FeatherPanel/backend.yml?branch=develop&label=Backend&style=for-the-badge&logo=php&logoColor=white)](https://github.com/tanmay712/FeatherPanel/actions/workflows/backend.yml)
[![Async Runner](https://img.shields.io/github/actions/workflow/status/tanmay712/FeatherPanel/runner.yml?branch=develop&label=Async%20Runner&style=for-the-badge&logo=rust&logoColor=white)](https://github.com/tanmay712/FeatherPanel/actions/workflows/runner.yml)
[![License](https://img.shields.io/github/license/tanmay712/FeatherPanel?style=for-the-badge&color=2563eb)](https://github.com/tanmay712/FeatherPanel/blob/develop/LICENSE)

</div>

---

## ⚠️ Development branch

<table>
<tr>
<td width="56">🚨</td>
<td>

**Do not run `develop` in production.**

This branch ships experimental features that may be unstable, incomplete, or unsafe. For live environments, deploy a tagged OrveX Panel release (see [Deploying OrveX Panel](#-deploying-orvex-panel)). The upstream [FeatherPanel docs](https://docs.mythical.systems/docs) still apply to everything that is not OrveX-specific.

</td>
</tr>
</table>

---

## ✨ What OrveX Panel adds

Everything below ships **in this repository** and is active as soon as the panel starts, with no marketplace installs needed.

### Bundled addons (`backend/storage/addons/`)

| Addon | What it does |
| --- | --- |
| **Billing Core** (`billingcore`) | Core billing: user credits, invoices and admin billing management. Required by the other billing addons. |
| **Billing Plans** (`billingplans`) | Sell servers as renewable plans with credit-based billing (WHMCS-style subscriptions, renewals, suspensions). |
| **Billing Resources** (`billingresources`) | Gives users an account-level pool of resources (memory, CPU, disk) that they can split across multiple servers. |
| **Billing Resources: New Servers** (`billingresourcesnewservers`) | Lets users create servers from their purchased resources. |
| **Billing Resources: Store** (`billingresourcesstore`) | Lets users buy resources, or packages of resources, with credits. |
| **Billing AFK** (`billingafk`) | Rewards users with credits for staying on the AFK page. |
| **Billing Links** (`billinglinks`) | Users earn credits by visiting links (Linkvertise, LinkPays, GyaniLinks, ShareUS). |
| **Billing Redeem** (`billingredeem`) | Coupon codes that users redeem for credits. |
| **Billing Referrals** (`billingreferrals`) | Referral system that rewards users with credits for inviting new users. |
| **Pterodactyl Panel API** (`pterodactylpanelapi`) | Brings back a Pterodactyl-style API (application and client endpoints) for tools built against the Pterodactyl API. |
| **DiscordPlus** (`discordplus`) | Search users by Discord ID and optionally require Discord account linking. |
| **WidgetBot** (`widgetbot`) | Embeds your Discord server in the panel through WidgetBot. |
| **Minecraft Datapack Installer** (`minecraftdatapackinstaller`) | Install Vanilla Tweaks datapacks straight from the server page. |
| **CryptIO** (`cryptio`) | Wrapper to encrypt and decrypt strings in the MythicalPanel encryption format. |
| **DevUtils** (`devutils`) | Helper utilities for plugin developers. |
| **Let It Snow** (`letitsnow`) | Snowfall effect across the panel. |
| **Let's Celebrate** (`letscelebrate`) | New-year fireworks effect. |

They are active as soon as the panel starts; configure them under **Admin → Plugins**. Their database tables are created by the normal `php cli migrate` run (Docker runs it on every start).

### Translations and spells

- **19 languages** in `backend/public/translations/`: Amharic, Czech, German, Spanish (Latin America), French, Croatian, Hungarian, Italian, Japanese, Khmer, Dutch, Polish, Portuguese, Romanian, Russian, Slovak, Serbian, Turkish, plus English. Choose which ones are offered in **Admin → Translations**.
- **12 spells (eggs)** in `backend/storage/eggs/`: Minecraft (Vanilla, Forge, BungeeCord, Pumpkin), Rust, CS:GO, Team Fortress 2, Insurgency, custom Source engine games, discord.py bots, Mumble and TeamSpeak 3. Import them with **Admin → Spells → Import Spell**.

### Rebuilding addon frontends

The addon UIs are prebuilt into `Frontend/Components/<addon>/dist/`. After changing an addon's Vue source, rebuild with:

```bash
make addons            # or: scripts/build-addon-frontends.sh [addon ...]
```

---

## 🐳 Deploying OrveX Panel

**Option A: build on your server (no registry needed)**

```bash
git clone https://github.com/tanmay712/FeatherPanel.git orvexpanel && cd orvexpanel
docker compose -f docker-compose.v2.git.yml up -d --build
```

**Option B: use prebuilt images from GHCR**

The Docker workflows publish OrveX images as `ghcr.io/tanmay712/orvexpanel-*`, and `docker-compose.yml` uses those images.

1. Enable workflows once under the repository's **Actions** tab (GitHub turns them off on forks by default).
2. Pushing to `develop` builds the `:dev` images (*Docker Dev* workflow). Pushing a version tag such as `v1.0.0` (`git tag v1.0.0 && git push origin v1.0.0`) builds `:latest` (*Docker Release* workflow).
3. Make the packages public under GitHub → **Packages** so servers can pull them without logging in, then run `docker compose up -d`.

**Upgrading an existing install:** on startup the backend copies in any bundled addon or translation that your persistent volumes don't have yet. Each addon is seeded only once, so addons you uninstall stay uninstalled and marketplace updates are never overwritten. Volume, container and database names keep their `featherpanel_*` names on purpose, so existing installs upgrade in place without losing data.

---

## 🧭 Quick navigation

<table>
<tr>
<th align="left">📖 Documentation</th>
<th align="left">🧩 Developer reference</th>
<th align="left">💬 Community</th>
</tr>
<tr>
<td valign="top">

- [Installation guides](https://docs.mythical.systems/docs)
- [Configuration](https://docs.mythical.systems/docs)
- [Releases](https://github.com/mythicalltd/featherpanel/releases)
- [Changelog](https://github.com/mythicalltd/featherpanel/blob/develop/CHANGELOG.md)

</td>
<td valign="top">

- [icanhasfeatherpanel](https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/) widgets, permissions, events
- [OpenAPI / Redoc](https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/api/) full API reference

</td>
<td valign="top">

- [Discord](https://discord.mythical.systems)
- [GitHub Issues](https://github.com/mythicalltd/featherpanel/issues)
- [Contributors graph](https://github.com/mythicalltd/featherpanel/graphs/contributors)

</td>
</tr>
</table>

---

## 🏗️ Stack

<table>
<tr>
<th>Layer</th>
<th>Technology</th>
<th>Path</th>
</tr>
<tr>
<td>🐘 Panel API</td>
<td>PHP 8.5</td>
<td><code>backend/</code></td>
</tr>
<tr>
<td>⚛️ Web UI</td>
<td>Next.js · React · TypeScript</td>
<td><code>frontendv2/</code></td>
</tr>
<tr>
<td>🦀 Async jobs</td>
<td>Rust (<code>async-runner</code>)</td>
<td><code>runner/</code></td>
</tr>
<tr>
<td>📦 Installer</td>
<td>Bash</td>
<td><code>installer/</code></td>
</tr>
</table>

Docker images for the backend, frontend, and async runner are published through the release workflows listed below.

---

## 📚 icanhasfeatherpanel public developer docs

**icanhasfeatherpanel** is FeatherPanel’s static developer reference. No running panel is required to browse it.

<details open>
<summary><strong>What’s included</strong></summary>

<br />

| Section                  | Contents                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------- |
| 🧩 **Plugins**           | Full Markdown guides for building addons (`conf.yml`, backend, frontend, SDK, packaging, AI recipes) |
| 🧭 **Pages**             | Every frontend Next.js route/slug (`pages/all.json`) for UI navigation guidance                      |
| 🧩 **Widgets**           | Injection points as HTML + `.md` + `.json`                                                           |
| ⌨️ **CLI**               | All `featherpanel` / `php cli` commands + production usage (`cli/usage.md`, `cli/all.json`)          |
| ⚙️ **Settings**          | Admin settings keys, types, options, categories from `SettingsController` (`settings/all.json`)      |
| 🧰 **Installer**         | `install.bash` flags, menus, automation env vars (`installer/guide.md`)                              |
| 🔐 **Permissions**       | Every permission node as HTML + `.md` + `.json` (`all.json`)                                         |
| 📡 **Events**            | Plugin hooks as HTML + `.md` + `.json` (`all.json`)                                                  |
| 🔌 **API reference**     | Redoc UI + raw `openapi.json`                                                                        |
| 🧠 **RAG index**         | `catalog.json` + `llms.txt` listing every machine-readable doc                                       |
| 🔑 **OAuth2 playground** | OAuth2 docs (live API calls still need a panel)                                                      |

</details>

<details>
<summary><strong>🌐 Live site (GitHub Pages)</strong></summary>

<br />

**https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/**

Plugin authoring (Markdown + AI index):

**https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/plugins/**

RAG / machine-readable index:

- **https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/rag/**
- **https://mythicalltd.github.io/FeatherPanel/catalog.json**
- **https://mythicalltd.github.io/FeatherPanel/llms.txt**

Examples for crawlers: `…/pages/all.json`, `…/cli/all.json`, `…/cli/usage.md`, `…/settings/all.json`, `…/installer/guide.md`, `…/permissions/all.json`, `…/events/all.json`, `…/widgets/index.json`, `…/api/openapi.json`, `…/plugins/ai-guide.md`.

</details>

<details>

<summary><strong>🛠️ Build locally</strong></summary>

<br />

Hand-authored inputs live in `frontendv2/icanhas/` (plugin Markdown, auth guides, assets, schemas). One command - `pnpm export:docs` - builds the **entire** `public/icanhasfeatherpanel/` tree (widgets, pages, permissions, events, API + OpenAPI, CLI, settings, installer, plugins/auth indexes, RAG). That output is gitignored and produced at ship time for **both** GitHub Pages (`pnpm build:public-docs`) and Docker/panel images (host `export:docs` then `frontendv2` image build, or `pnpm build:with-docs` / `make frontend`).

```bash
# 1. Generate OpenAPI from PHP controller annotations
cd backend
COMPOSER_ALLOW_SUPERUSER=1 composer openapi

# 2. Export docs + assemble static GitHub Pages site
cd ../frontendv2
pnpm install
pnpm build:public-docs

# Output lands in ../docs-site/
# Serve it with any static file server, e.g.:
python3 -m http.server 8080 --directory ../docs-site
```

For a normal panel image / local Next build that should include `/icanhasfeatherpanel/`:

```bash
cd frontendv2
pnpm build:with-docs   # export:docs then pnpm build
```

Optional environment variables for `build:public-docs`:

| Variable          | Purpose                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| `DOCS_OUTPUT_DIR` | Output directory (default: `docs-site/`)                                               |
| `DOCS_BASE_PATH`  | URL prefix for GitHub Pages project sites (CI sets `/FeatherPanel` from the repo name) |
| `OPENAPI_JSON`    | Path to the generated OpenAPI file                                                     |

</details>

---

## 🔄 CI & workflows

<table>
<tr>
<th>Workflow</th>
<th>Purpose</th>
</tr>
<tr>
<td><a href="workflows/frontend.yml">frontend.yml</a></td>
<td>Builds the Next.js panel UI</td>
</tr>
<tr>
<td><a href="workflows/backend.yml">backend.yml</a></td>
<td>PHP lint, migrations, and backend tests</td>
</tr>
<tr>
<td><a href="workflows/runner.yml">runner.yml</a></td>
<td>Builds and tests the Rust async runner</td>
</tr>
<tr>
<td><a href="workflows/shell-lint.yml">shell-lint.yml</a></td>
<td>ShellCheck + syntax validation for the installer</td>
</tr>
<tr>
<td><a href="workflows/docs-pages.yml">docs-pages.yml</a></td>
<td>Generates icanhasfeatherpanel (not committed) + OpenAPI and deploys the static site to GitHub Pages</td>
</tr>
<tr>
<td><a href="workflows/docker-dev.yml">docker-dev.yml</a></td>
<td>Dev Docker images → GHCR (<code>develop</code>)</td>
</tr>
<tr>
<td><a href="workflows/docker-release.yml">docker-release.yml</a></td>
<td>Release Docker images on version tags</td>
</tr>
<tr>
<td><a href="workflows/docker-oci-release.yml">docker-oci-release.yml</a></td>
<td>OCI release artifacts</td>
</tr>
<tr>
<td><a href="workflows/codeql.yml">codeql.yml</a></td>
<td>Security analysis (JS/TS)</td>
</tr>
<tr>
<td><a href="workflows/dependency-review.yml">dependency-review.yml</a></td>
<td>Flags vulnerable dependency changes in PRs</td>
</tr>
</table>

---

## 📊 Code statistics

<!-- COUNT-STATS:START -->

_Last updated: 2026-11-19T22:14:17.270Z_

| Extension | Files | Lines |
| --- | ---: | ---: |
| `.php` | 962 | 223,921 |
| `.tsx` | 759 | 218,342 |
| `.ts` | 268 | 42,475 |
| `.json` | 23 | 28,224 |
| `.yaml` | 5 | 7,825 |
| `.css` | 8 | 6,101 |
| `.rs` | 32 | 4,777 |
| `.sql` | 253 | 4,621 |
| `.yml` | 32 | 3,225 |
| **Total** | 2,342 | 539,511 |

<!-- COUNT-STATS:END -->

---

## 🚀 Try it (stable installer)

These commands install the latest **stable upstream FeatherPanel** build. They do **not** install OrveX Panel; use the Docker steps in [Deploying OrveX Panel](#-deploying-orvex-panel) for that.

<table>
<tr>
<th align="left">🐧 Linux</th>
<th align="left">🪟 Windows</th>
</tr>
<tr>
<td valign="top">

```bash
curl -sSL https://get.featherpanel.com/stable.sh | bash
```

</td>
<td valign="top">

**PowerShell**

```powershell
iwr https://get.featherpanel.com/stable.ps1 | iex
```

**CMD**

```cmd
powershell -ExecutionPolicy Bypass -Command "iwr https://get.featherpanel.com/stable.ps1 | iex"
```

</td>
</tr>
</table>

<details>
<summary><strong>After installation</strong></summary>

<br />

1. Register the first account it becomes the admin automatically.
2. Follow the [configuration docs](https://docs.mythical.systems/docs).
3. Report OrveX-specific bugs on [GitHub Issues](https://github.com/tanmay712/FeatherPanel/issues).

</details>

---

## 🤝 Contributing

Contributions are welcome. Please read the [contributing guide](CONTRIBUTING.md) and [code of conduct](CODE_OF_CONDUCT.md) before opening a pull request.

<div align="center">

[![Contributors](https://contrib.rocks/image?repo=mythicalltd/featherpanel)](https://github.com/mythicalltd/featherpanel/graphs/contributors)

</div>

---

## 📄 License

OrveX Panel is a modified version of [FeatherPanel](https://github.com/MythicalLTD/FeatherPanel) (Copyright © FeatherPanel Contributors / Mythical Systems) and, like the original, is licensed under the **[GNU Affero General Public License v3.0](../LICENSE)**. If you run a modified version for users over a network, the AGPL requires you to offer them its source code.

---

<div align="center">

<sub>OrveX Panel, built on FeatherPanel, made with ❤️ by <a href="https://mythical.systems"><strong>Mythical Systems</strong></a> and contributors</sub>

<br /><br />

<a href="https://docs.mythical.systems/docs">Documentation</a>
&nbsp;·&nbsp;
<a href="https://mythicalltd.github.io/FeatherPanel/icanhasfeatherpanel/">Developer docs</a>
&nbsp;·&nbsp;
<a href="https://discord.mythical.systems">Discord</a>
&nbsp;·&nbsp;
<a href="https://github.com/tanmay712/FeatherPanel/issues">Issues</a>
&nbsp;·&nbsp;
<a href="https://github.com/tanmay712/FeatherPanel/releases">Releases</a>

</div>
