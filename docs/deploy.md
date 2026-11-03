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
Publish both pseudopotential packs (`docs/releases.md`, "Data packs"):

```bash
uv run --python 3.11 python -m app.releases.publish_data \
  ~/pseudo/pslibrary-pbe --name pslibrary-pbe --version 1.0.0 \
  --api-url "$ATOMFIELD"
```

```bash
uv run --python 3.11 python -m app.releases.publish_data \
  ~/pseudo/pslibrary-rel-pbe --name pslibrary-rel-pbe --version 1.0.0 \
  --api-url "$ATOMFIELD"
```

Then the release:

```bash
uv run --python 3.11 python -m app.releases.publish --api-url "$ATOMFIELD"
```

A tunnel may limit uploads: Cloudflare's free plan stops at 100 MB, which
`pslibrary-rel-pbe` is over. Publish a bigger pack on the server itself,
with `--api-url http://127.0.0.1:8000`.

## 6. Set up people and clusters

Make a lab and give it its workflows (`docs/labs.md`). Each person then
connects their cluster (`docs/cluster-agent.md`). Until someone has one,
Run stays off and **Run on** offers to add one.

## From a published image

A server can run an image built elsewhere instead of a copy of the code.
On your own computer, from a clean copy of the committed code (so nothing
uncommitted or local goes in), build for the server's kind of machine
(`docker version --format '{{.Server.Os}}/{{.Server.Arch}}'` on the
server says which) and push it to GitHub's registry:

```bash
docker buildx build --platform linux/arm64 \
  -t ghcr.io/OWNER/atomfield:TAG --push .
```

The image holds the server's code and the built web app; scripts still
arrive only as releases (step 5). On the server, put three files in one
folder: `docker-compose.server.yml` saved as `docker-compose.yml`,
`.env.example` and `backup.sh`. Make `.env` as in step 2, add
`ATOMFIELD_IMAGE=ghcr.io/OWNER/atomfield:TAG`, log in with
`docker login ghcr.io` if the image is private, and start it with
`docker compose up -d`. To update, push a new tag, change
`ATOMFIELD_IMAGE`, and run `docker compose up -d` again.

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

The server runs no jobs by default. To run Quantum ESPRESSO and
Wannier90 on this machine too, start its **worker**: the same agent
people run on clusters, in an image that also holds the programs
(`Dockerfile.worker`). This needs a server running a published image
(above). **AtomField server** then shows under **Run on** for everyone
signed in; the workflows ticked for each person still decide what they
can run.

On your own computer, after pushing the server image, build the worker
on top of it, for the same kind of machine and with the same TAG:

```bash
docker buildx build --platform linux/amd64 -f Dockerfile.worker \
  --build-arg ATOMFIELD_IMAGE=ghcr.io/OWNER/atomfield:TAG \
  -t ghcr.io/OWNER/atomfield-worker:TAG --push .
```

Built on a Mac for `linux/amd64`, this is emulated and takes a while.
Releases are compiled for `linux-x86_64` only, so the worker needs an
x86 server.

On the server, add to `.env` a new `HOUSE_AGENT_TOKEN` (from
`openssl rand -hex 32`) and `ATOMFIELD_WORKER_IMAGE`, and optionally
`WORKER_CPUS` (default 2) and `WORKER_MAX_JOBS` (default 1). Jobs run
as uid 1000, so give that the work folder:

```bash
mkdir -p work
```

```bash
sudo chown 1000:1000 work
```

```bash
docker compose --profile house up -d
```

```bash
docker compose logs -f worker
```

Jobs share this machine's CPUs and memory with the API and the
database; `WORKER_CPUS` caps them. A step sized for a cluster node
(16 CPUs) runs here on `WORKER_CPUS` MPI processes, since MPI refuses
to start more than the machine has cores: keep `WORKER_CPUS` at or
below its physical cores (`lscpu`: cores per socket times sockets;
`nproc` counts hyperthreads too). Each finished run is zipped
into `storage/` and its folder in `work/` removed, so watch the disk.
The programs are conda-forge's generic builds: fine for small systems
and teaching, slower than a cluster's own.

An agent anywhere can be held to fewer CPUs per job the same way, with
`max_cpus = N` in its settings file or `ATOMFIELD_MAX_CPUS`.
