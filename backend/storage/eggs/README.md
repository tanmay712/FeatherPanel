# Bundled spells (eggs)

Pterodactyl-compatible (`PTDL_v2`) eggs from the official FeatherPanel
[Games](https://github.com/featherpanel-com/Games) and
[Applications](https://github.com/featherpanel-com/Applications) repositories,
bundled so they are available without network access.

| Folder | Spells |
| --- | --- |
| `games/` | Vanilla Minecraft, Forge Minecraft, BungeeCord, Pumpkin, Rust, Counter-Strike: Global Offensive, Team Fortress 2, Insurgency, Custom Source Engine Game |
| `applications/` | Discord.py, Mumble Server, TeamSpeak 3 Server |
| `free-tier/` | Node.js, Python, Bun, Java, C# (.NET), Rust, Lua (Luvit), MongoDB 7, MariaDB 11.5, PostgreSQL 16, Redis 7 (the stacks behind **Create server**; see below) |

## Free servers (`free-tier/`)

The spells behind the **Create server** page for free servers. Admins install them in one click from
**Admin → Free servers → Install bundled spells**, which imports them into a "Free servers" realm and
picks them for their stacks. They are based on the MIT-licensed
[pelican-eggs](https://github.com/pelican-eggs) eggs (see `free-tier/LICENSE-pelican-eggs.md`). Every
file gets a short name, a `PTDL_v2` header and a fixed uuid (so the installer can find it again); other
changes are listed below.

| File | Stack | Based on | Other changes |
| --- | --- | --- | --- |
| `orvex-free-nodejs.json` | Node.js | [generic/nodejs/egg-pterodactyl-nodejs-generic.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/nodejs/egg-pterodactyl-nodejs-generic.json) | the server shows as running once the app starts |
| `orvex-free-python.json` | Python | [generic/python/egg-pterodactyl-python-generic.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/python/egg-pterodactyl-python-generic.json) | the server shows as running once the app starts |
| `orvex-free-bun.json` | Bun | [generic/bun/egg-pterodactyl-bun.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/bun/egg-pterodactyl-bun.json) | the server shows as running once the app starts |
| `orvex-free-java.json` | Java | [generic/java/egg-pterodactyl-java-generic.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/java/egg-pterodactyl-java-generic.json) | Java 21 is the default image, the Java 16 image tag is fixed, JARFILE defaults to app.jar; the server shows as running once the app starts |
| `orvex-free-csharp.json` | C# (.NET) | [generic/c#/egg-pterodactyl-generic-c.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/c%23/egg-pterodactyl-generic-c.json) | the server shows as running once the app starts |
| `orvex-free-rust.json` | Rust | [generic/rust/egg-pterodactyl-rust-generic.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/rust/egg-pterodactyl-rust-generic.json) | the server shows as running once the app starts |
| `orvex-free-lua.json` | Lua (Luvit) | [generic/lua/luvit/egg-pterodactyl-luvit-generic.json](https://github.com/pelican-eggs/generic/blob/eec3d4b153ccb8b901905b486f29d4d199154f5b/lua/luvit/egg-pterodactyl-luvit-generic.json) | the server shows as running once the app starts |
| `orvex-free-mongodb.json` | MongoDB 7 | [database/nosql/mongodb/egg-mongo-d-b7.json](https://github.com/pelican-eggs/database/blob/efd5983aa52aa0446c11bc6d8f696f788cdfc8e7/nosql/mongodb/egg-mongo-d-b7.json) | none |
| `orvex-free-mariadb.json` | MariaDB 11.5 | [database/sql/mariadb/egg-maria-d-b115.json](https://github.com/pelican-eggs/database/blob/efd5983aa52aa0446c11bc6d8f696f788cdfc8e7/sql/mariadb/egg-maria-d-b115.json) | converted from the Pelican PLCN_v1 format |
| `orvex-free-postgresql.json` | PostgreSQL 16 | [database/sql/postgres/egg-postgres16.json](https://github.com/pelican-eggs/database/blob/efd5983aa52aa0446c11bc6d8f696f788cdfc8e7/sql/postgres/egg-postgres16.json) | none |
| `orvex-free-redis.json` | Redis 7 | [database/redis/redis-7/egg-redis-7.json](https://github.com/pelican-eggs/database/blob/efd5983aa52aa0446c11bc6d8f696f788cdfc8e7/redis/redis-7/egg-redis-7.json) | converted from the Pelican PLCN_v1 format; variable rules written as text |

Database stacks get a random password for every server, so no two free servers share the egg's default.

## Importing

1. Open **Admin → Spells** in OrveX Panel.
2. Click **Import Spell**, pick the realm, and upload one of the JSON files from this folder.

Spells and Pterodactyl eggs are cross-compatible, so you can also import these files into a Pterodactyl panel.
