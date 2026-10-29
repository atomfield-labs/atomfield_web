# Publishing the scripts

AtomField runs the calculation scripts from afscripts. Agents never
need afscripts copied to them: the server hands out **releases**, and
each agent downloads the release a job needs.

## What a release is

A release is one wheel, the zip file a Python package ships as, with
the package's `catalog.json` inside. The catalog lists the tasks and
their flags, so the code and the description of how to call it always
travel together.

Each release has:

- a **version**, the one in `pyproject.toml` plus the git commit it
  was built from: `0.1.0+g2e6d386`;
- a **fingerprint**, the sha256 of the wheel. Agents refuse a
  download whose fingerprint differs from the server's.

A release never changes. Any change, even a one-line fix, is a new
commit and so a new release.

## Publish one

Commit your change in the afscripts repository, then from the
AtomField repository:

```bash
uv run --python 3.11 python -m app.releases.publish \
  --repo ~/afscripts --ref HEAD
```

The command:

1. copies the commit out of git (unfinished files in your working
   folder stay behind, committed or not);
2. puts the commit's `catalog.json` inside the package;
3. adds the commit to the version;
4. builds the wheel with `uv build`;
5. uploads it with the administrator key (`ADMIN_API_KEY`, read from
   the environment or `.env`). Use `--api-url` for another server.

The server checks the wheel without running it. It must be pure
Python, carry `<package>/catalog.json`, and contain every module its
catalog names. Then it becomes the release new runs use; the
pipeline editor shows its tasks at once.

Publishing the same commit again changes nothing (`already
published`). The server refuses the same version with different
contents.

## What runs where

- A run uses the release that was newest when it was submitted, for
  all its jobs and retries. To use a newer release, run the pipeline
  again.
- `GET /api/releases/current` shows the newest release.
- The **Get files** panel of a cluster run shows the release that
  made it; each job folder's `.af_made_with` note records the scripts
  and data packs that ran there.
- Runs from before the first release use the catalog file the server
  starts with (`CATALOG_PATH`); their agents need their own copy of
  the scripts (`pack_dir`).

## Ready-made pipelines

The editor's **Prebuilt Pipelines** come from the release too, so a
template always matches the tasks it calls. Each is a TOML file in
afscripts' `catalog/pipelines/`: its example structures (files beside
it), then its steps in the order they run, each naming a task, the
nodes it reads from (`after`) and only the values that differ from
the task's defaults:

```toml
[[structures]]
key = "structure_fe"
file = "structures/fe_bcc_primitive.in"

[[steps]]
key = "ahc_scf"
task = "ahc_scf"
label = "SCF with spin-orbit"
after = ["structure_fe"]
parameters = { magnetization = "Fe=0.5" }
```

A step may only follow what is listed before it, so a template cannot
loop. The export copies the structures' text into `catalog.json`, and
stops on a template naming an unknown task or parameter. The server
checks the values themselves when the release is published: a broken
template refuses the release. `GET /api/pipeline-templates` lists the
templates of the newest release; the editor lays each one out left to
right and fills in every other setting from the task's defaults.

What a release does not carry: the Python packages the scripts import
(ase, numpy...) and the engines (Quantum ESPRESSO, xTB). Each machine
provides those once: a conda environment, and the cluster's modules
loaded by the agent's setup lines.

## Data packs

Big files that scripts read but that almost never change, such as
pseudopotentials, travel as **data packs**: a zip with a name and a
version, published once, downloaded once per machine. They stay out
of the release, which would otherwise carry them again with every
commit.

A task names the packs it reads in its TOML file in afscripts, with
the environment variable that should hold the pack's folder:

```toml
[[data]]
name = "pslibrary-rel-pbe"
version = "1.0.0"
env = "ESPRESSO_PSEUDO"
```

Publish the pack before the release that names it (a release naming
a pack that does not exist is refused):

```bash
uv run --python 3.11 python -m app.releases.publish_data \
  ~/pseudo/pslibrary-rel-pbe --name pslibrary-rel-pbe --version 1.0.0
```

The command zips the folder the same way every time (hidden files
left out), so publishing unchanged files again sends nothing. The
server keeps the zip only if it matches the fingerprint the command
announced, and never accepts other contents under the same version:
a change is a new version, named by a new release.

Before a job starts, its agent downloads each pack it needs (once per
machine, into `<work>/data/`), checks the fingerprint, unpacks it, and
sets the variable: `ESPRESSO_PSEUDO=<work>/data/pslibrary-rel-pbe-...`.
The job folder's `.af_made_with` note lists the packs the job used.

`GET /api/data-packs` lists the published packs. Packs over 100 MB do
not fit through a Cloudflare tunnel on the free plan; split them (for
example one pack per functional).
