# Putting AtomField on a server

One machine holds the web app, the API, the database and the queue. Jobs
run elsewhere, on clusters, through agents that call this server
(`docs/cluster-agent.md`). The server holds no scripts until you publish
a release, and then only compiled.

## What you need

- A Linux machine that stays on, with Docker and Docker Compose.
- A fixed https name for it. Google's sign-in and every agent's settings
  store that name, so it must not change: a quick tunnel, whose name
  changes at each start, will not do.
- A Google sign-in registration, with its client ID and secret.
- On your own computer: Docker and the afscripts repository, to publish
  releases (`docs/releases.md`).

## 1. Get the code

```bash
git clone -b phase-5-slurm https://github.com/atomfield-labs/atomfield_web
```

```bash
cd atomfield_web
```

Do not ask for submodules: a server needs no scripts folder.

## 2. Make its secrets

`.env` holds this server's secrets. It stays on this machine: git ignores
it, the image leaves it out, and it is never copied from another server.

```bash
cp .env.example .env
```

```bash
chmod 600 .env
```

Replace each `change-me` with its own value from `openssl rand -hex 32`.
The server refuses to start while one is left. `AI_KEY_SECRET` encrypts each
person's AI key (`docs/ai-help.md`): with it removed the AI buttons stay off,
and if it changes people add their keys again. Then fill in:

| Setting | Value |
|---|---|
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | from Google |
| `OIDC_REDIRECT_URI` | `https://your.name/api/auth/callback` |
| `OWNER_EMAILS` | your address, as Google gives it |

Add the same redirect address in Google's console.

## 3. Start it

```bash
docker compose up -d --build
```

The first build takes a few minutes. Each start brings the database up to
date first, backing it up if anything needs changing. To check it:

```bash
curl -s http://127.0.0.1:8000/health
```

Port 8000 listens on this machine only. If you started once with the
example's values, its database took that password. To start again from
nothing:

```bash
docker compose down -v
```

## 4. Give it its https name

Whatever serves the name forwards everything to
`http://127.0.0.1:8000`. If that runs on another machine, set `API_BIND`
in `.env` to an address only it can reach.

Live updates arrive as a stream, so it must not hold responses back
(with nginx, `proxy_buffering off`). With Caddy on this machine, this is
all it takes, if the name points here and ports 80 and 443 reach it:

```
your.name {
	reverse_proxy 127.0.0.1:8000
}
```

Leave `TRUST_PROXY_HEADERS` false unless it is a Cloudflare tunnel. The
limits on sign-ins and pairings then count everyone behind the proxy as
one address, which is fine for one lab.

## 5. Publish the scripts

Until then the server has no tasks. On your own computer, in the
AtomField folder, give the commands the server's address and its key
(nothing shows while you paste it):

```bash
export ATOMFIELD=https://your.name
```

```bash
read -rs ADMIN_API_KEY && export ADMIN_API_KEY
```

Data packs go first, since a release naming a missing one is refused.
Publish each pack its tasks name (`docs/releases.md`, "Data packs"):

```bash
uv run --python 3.11 python -m app.releases.publish_data \
  ~/pseudo/pslibrary-pbe --name pslibrary-pbe --version 1.0.0 \
  --api-url "$ATOMFIELD"
```

Then the release:

```bash
uv run --python 3.11 python -m app.releases.publish --api-url "$ATOMFIELD"
```

A tunnel may limit uploads (Cloudflare's free plan stops at 100 MB).
Publish a bigger pack on the server itself, with
`--api-url http://127.0.0.1:8000`.

## 6. Set up people and clusters

Make a lab and give it its workflows (`docs/labs.md`). Each person then
connects their cluster (`docs/cluster-agent.md`). Until someone has one,
Run stays off and **Run on** offers to add one.

## Updating

```bash
git pull
```

```bash
docker compose up -d --build
```

Files and data stay. Agents reconnect by themselves, and jobs already on
a cluster keep running meanwhile.

## What to keep safe

| Where | What |
|---|---|
| `.env` | this server's secrets |
| the `pg_data` volume | accounts, labs, sessions, the record of runs |
| `storage/` | releases, data packs, uploads, the files steps show |
| `backups/` | database copies, taken before each migration |

Results stay on the clusters. To copy the database every night, keeping
one per weekday, add this with `crontab -e`, using this folder's path:

```
0 2 * * * cd /path/to/atomfield_web && ./backup.sh
```

A copy on the same disk does not survive that disk, so also copy
`backups/`, `storage/` and `.env` to another machine now and then. To put
a copy back, into a database with nothing in it yet:

```bash
docker compose up -d db
```

```bash
gunzip -c backups/nightly-Mon.sql.gz \
  | docker compose exec -T db psql -q -U postgres atomfield_db
```

```bash
docker compose up -d
```

## Running jobs on the server itself

The server runs no jobs by default. Its image holds no scientific
programs, so `docker compose --profile house up -d`, with
`HOUSE_AGENT_TOKEN` set, runs only tasks that need none; **AtomField
server** then shows under **Run on** for everyone. To run real programs
on this machine, install them on it and treat it as a cluster: run an
agent there as `docs/cluster-agent.md` describes, with `process` as how
jobs run.
