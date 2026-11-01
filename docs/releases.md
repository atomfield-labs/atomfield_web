# Publishing the scripts

AtomField runs the calculation scripts from afscripts. Agents never
need afscripts copied to them: the server hands out **releases**, and
each agent downloads the part of a release a job needs.

The scripts are the product, so they are never readable outside your
own computer: afscripts lives in a **private** GitHub repository (the
AtomField server code, `atomfield_web`, can be public), and a release
holds only compiled code.

## What a release is

A release is one **bundle**, a zip file with:

- `catalog.json`, which lists the tasks, pipelines and workflows and
  their flags;
- one file per **package** (what a lab sees as a workflow) and per
  kind of computer: `quantum_espresso`, `wannier90` and `nanoreactor`,
  each for `darwin-arm64` (a Mac) and `linux-x86_64` (a cluster).
  Each file is about half a megabyte.

A package's file holds that package's scripts and what they import, as
compiled modules (`.so`), empty `__init__.py` files, and the small
tables the scripts read. It holds no `.py` file, no docstring and no
comment. A job gets only its own package's file, built for its agent's
machine, so a lab given Quantum ESPRESSO never receives the Nanoreactor
code.

Each release has:

- a **version**, the one in `pyproject.toml` plus the git commit it
  was built from: `0.1.0+gb0c454a`;
- a **fingerprint** per file, the sha256 of each. Agents refuse a
  download whose fingerprint differs from the server's.

A release never changes. Any change, even a one-line fix, is a new
commit and so a new release.

## Publish one

Commit your change in the afscripts repository, make sure Docker is
running (the Linux build happens in a container), then from the
AtomField repository:

```bash
uv run --python 3.11 python -m app.releases.publish \
  --repo ~/afscripts --ref HEAD
```

The command:

1. copies the commit out of git (unfinished files in your working
   folder stay behind, committed or not);
2. adds the commit to the version;
3. stops there if the server already has that version;
4. finds the modules each package needs by following its tasks'
   imports, and compiles them with Cython, once per kind of computer:
   a Mac natively, and Linux in the `manylinux2014` image, whose old C
   library (glibc 2.17) is the oldest a cluster is likely to have. One
   build serves every Python from 3.11 on;
5. packs each package's file from the compiled modules only, and
   checks that nothing readable went in;
6. uploads the bundle with the administrator key (`ADMIN_API_KEY`,
   read from the environment or `.env`). Use `--api-url` for another
   server.

It takes a few minutes, most of it the Linux build. To publish for one
kind of computer while testing, add `--machines darwin-arm64`.

The server checks the bundle without running any of it. It must hold a
file for every package on every machine it names, each file must
contain every module its package's tasks name, and nothing readable
(`.py`, `.c`, `.h`...) may be inside. Then it becomes the release new
runs use; the pipeline editor shows its tasks at once.

Publishing the same commit again changes nothing (`already
published`). The server refuses the same version with different
contents; a rebuild of the same commit need not match byte for byte,
so the first copy is the one that stays.

## What runs where

- A run uses the release that was newest when it was submitted, for
  all its jobs and retries. To use a newer release, run the pipeline
  again.
- A job runs `python -c "... import main ..."` on its package's
  compiled modules; no module is started with `python -m`, which
  needs source.
- A computer the release has no build for (a kind not listed above)
  fails the job with a message saying so. So does an agent from before
  this change: copy the agent again (`docs/cluster-agent.md`).
- `GET /api/releases/current` shows the newest release.
- The **Get files** panel of a cluster run shows the release that
  made it; each job folder's `.af_made_with` note records the scripts
  and data packs that ran there.
- Runs from before the first release use the catalog file the server
  starts with, if it has one (`CATALOG_PATH`); a server normally
  holds no scripts, and has no tasks until the first release.

## What this stops

Nobody who opens the server's storage, a cluster's work folder or a
release file finds code they can read, and the agent keeps what it
downloads in folders only its owner can open. QE input files in a job
folder stay readable, because Quantum ESPRESSO reads them and they are
the user's results. The agent and the server stay readable too; they
hold no science.

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

## Plots

A step's modal draws the plots its script leaves, in the browser. The
script says what to show and not how to draw it, so a new step's plots
need no change in the web app. Two things make a step show plots.

Its TOML file names them, which gives its modal a **Plots** tab:

```toml
[outputs.plots]
glob = "*_plots.json"
```

And its script writes them when it ends, with afscripts'
`utilities/plots.py`:

```python
from afscripts.utilities.plots import axis, curve, panel, plot, save_plots


def plots(self):
    shape = panel(
        axis("Step"),
        axis("Energy (eV)"),
        curves=[curve("Energy", self.steps, [self.energies])],
    )
    return [plot("Energy", shape)]


save_plots(self.jobname, self.plots, log)  # in exportData
```

`save_plots` writes `<job>_plots.json`. Trouble building or writing it
is said in the log and never fails the step, because the work the plot
shows is done. The file looks like this:

```json
{"format": 1, "plots": [{"title": "Band structure", "panels": [{
  "x": {"label": "", "ticks": [[0.0, "Γ"], [1.15, "X"]]},
  "y": {"label": "Energy (eV)", "range": [-10, 10], "lines": [0]},
  "curves": [{"name": "Bands", "x": [0.0, 0.1], "y": [[-5.6, -5.5]],
              "hover": "Band"}]}]}]}
```

- A step has one or more **plots**, which the modal offers by `title`.
- A plot has one or more **panels**, which stand side by side (`width`
  is each one's share) and share the first one's y axis. Two measures on
  different scales are two plots, never two axes on one.
- An **axis** has a `label` with its unit, and may have named `ticks`, a
  starting `range`, a `log` scale, and guide `lines`, each a place or a
  place and a name.
- A panel holds one of three things:
  - `curves`: each has a `name`, its `x`, and in `y` one line or many
    drawn alike. `null` leaves a gap. `hover` is what the tooltip calls
    each of many lines, `hidden` starts a curve off, and `fill` (`x` or
    `y`) washes the area down to zero on that axis.
  - `bars`: `labels`, `values`, and `hover` with more about each.
  - `graph`: `nodes` with `x`, `y`, `label` and `hover`, and `edges` as
    pairs of positions in that list.

Up to eight curves in a panel get a colour each. Text is shown as it is,
never as markup, and fields the web app doesn't know are ignored, so a
file can say what to show but nothing about how the page behaves. The
format number is there so an old page can say it can't read a new file.

The agent uploads a step's small text files when it ends, what the task
names first, 20 at most, each up to 2 MB; the **Artifacts** tab shows
them. A curve past 2,000 points is thinned to fit, and the tables keep
them all.

## What a release does not carry

A release does not carry the Python packages the scripts import (ase,
numpy...) or the engines (Quantum ESPRESSO, xTB). Each machine provides
those once: a conda environment, and the cluster's modules
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
