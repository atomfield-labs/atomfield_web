# Running AtomField jobs on your Slurm cluster

AtomField runs your pipelines on computers you already use. On a
cluster, a small program called the **agent** runs on the login node.
It asks AtomField for work, hands each job to Slurm with `sbatch`,
watches it, and reports back. Your results stay on the cluster; the
web app shows where they are and how to copy them.

The agent only makes outgoing HTTPS requests. Nothing connects into
your cluster, and AtomField never sees your cluster password.

## What you need

- SSH access to the cluster's login node.
- Outgoing HTTPS from the login node. Check with
  `curl -sI https://www.cloudflare.com | head -1` (expect `200`).
- Python 3.11 or newer. If the system Python is older, use a conda
  module (`module avail conda miniconda`).
- A Slurm account to charge, if your cluster asks for one
  (`sacctmgr -n show assoc user=$USER format=account`).

## 1. Copy the agent to the cluster

The agent is the `agent` folder plus a few small files of `app`;
nothing else of AtomField runs on the cluster. From your own computer,
in the AtomField folder (use what you type after `ssh`):

```bash
uv run --python 3.11 python -m agent.ship you@login.cluster.edu
```

It copies exactly the files the agent loads into `~/atomfield/code`,
replacing any older copy, and prints how many arrived. It also
installs a shortcut, `~/atomfield/agent`, which runs the agent with
the Python of step 2 from any folder: every command below starts with
it. If that Python lives elsewhere, add `--python /path/to/bin/python`
to the command above.

Run it again to update the agent later. A running agent keeps its
old copy until you restart it on the cluster (`~/atomfield/agent
stop`, then `start`; its Slurm jobs keep running meanwhile). Stopping the
copy with Ctrl+C is safe: run the command again to finish it.

If your cluster's SSH listens on another port, add a shortcut to
`~/.ssh/config`:

```
Host mycluster
    HostName login.cluster.edu
    User you
    Port 2222
```

and use `mycluster` instead of the address, here and in the answer
"Address to copy results from" in step 4. The scripts themselves
(afscripts) are not copied either: each job brings the release it
needs (see "Where the scripts come from").

## 2. Make a Python environment

On the login node:

```bash
module load miniconda3      # your cluster's name
conda create -y -p ~/atomfield/env --override-channels -c conda-forge \
  python=3.11 ase numpy httpx pydantic
conda clean -a -y
```

`--override-channels -c conda-forge` uses only the free, community
conda-forge packages. Simulation engines (Quantum ESPRESSO, ORCA...)
usually come from your cluster's own modules instead; step 3 loads
them for every job.

## 3. Log the agent in

```bash
~/atomfield/agent login
```

It asks for each setting, offering a default in brackets (Enter keeps
it):

| Question | Example answer |
|---|---|
| Address of the AtomField API | `https://atomfield.example.org` |
| How jobs run here | `slurm` |
| Work folder | `/home/you/atomfield` (must be visible to compute nodes) |
| Python that runs the job scripts | `/home/you/atomfield/env/bin/python` |
| Address to copy results from | your `ssh` target, e.g. `mycluster` |
| Extra `#SBATCH` options | `--account=my_project` |
| Setup line for each job | `module load quantum-espresso/7.2`, then Enter |

The settings are saved in `~/.config/atomfield/agent.toml`, readable
only by you (it holds the agent's token). Run `login` again to change
them; it keeps the token, and `login --pair` fetches a new one.

Each job's script runs in a login shell (`#!/bin/bash -l`), so
`module` works in the setup lines as it does when you log in. Quantum
ESPRESSO tasks start `pw.x` with `mpirun -np N` from the loaded
module. If your cluster wants `srun` instead, add one more setup
line: `export AFSCRIPTS_MPI_LAUNCHER="srun"`.

## 4. Approve its code

At the end, `login` shows a code and a link, such as
`https://atomfield.example.org/#pair/QKTW-MZRB`. Open the link while
signed in to AtomField, or in the pipeline editor choose **Run on**,
then **+ Add a cluster…**, and type the code. Check that the computer,
user and address are this login node's, name the cluster, and press
**Connect**. Within seconds `login` collects the agent's token and
saves the settings: nobody copies a token. A code lasts 10 minutes.

## 5. Start the agent

```bash
~/atomfield/agent start
```

```bash
~/atomfield/agent status
```

The agent keeps running after you log out, and restarts itself if it
crashes. In the web app, your cluster now shows **●** (online) under
**Run on**. The agent runs on the login node you started it on; if
you later land on another one, `status` tells you where it runs (log
in there, e.g. `ssh login1`, to stop it), and `start` refuses to begin
a second agent. Its log, `agent.log` in the work folder, is trimmed
past 10 MB (the older part is kept in `agent.log.1`).

To stop it: `~/atomfield/agent stop`. Your Slurm jobs keep running.

## Where the scripts come from

Every run uses one **release** of the scripts: a version published
to AtomField, such as `afscripts 0.1.0+gb0c454a` (the part after `+g`
is the git commit it was built from). A release holds one file per
**package**, the group of scripts a lab is given (Quantum ESPRESSO,
Wannier90...), and the scripts in it are compiled: nobody can read
them. The first job that needs a package downloads its file, the one
built for this computer, into `~/atomfield/releases/`, checks its
fingerprint (sha256), and unpacks it there; later jobs reuse it.

- All jobs of a run, retries included, use the release the run
  started with, even if a newer one is published meanwhile.
- Each job folder has a small `.af_made_with` note saying exactly
  which scripts and data packs ran there.
- A package's file is about half a megabyte, and stays beside the
  others. Your cluster holds only the packages its jobs used.
- `~/atomfield/releases/` and `~/atomfield/data/` can be opened only by
  you; the agent makes them so, even ones that already existed.

If an older agent ran here before, its `releases` folder may hold
readable copies of the scripts. After copying the new agent (step 1),
delete them, and the new agent downloads what it needs:

```bash
rm -rf ~/atomfield/releases
```

Data the scripts read, such as Quantum ESPRESSO pseudopotentials,
arrives the same way as **data packs**: downloaded once into
`~/atomfield/data/` when a job first needs them (a few hundred MB for
a full set of pseudopotentials; mind your quota). There is nothing to
download or unpack by hand.

To run your own copy of the scripts instead (for example, while you
edit them on the cluster), point the agent at it:

```bash
~/atomfield/agent login --pack-dir ~/afscripts/src
```

Every job then runs that copy, and its `.af_made_with` says so. Remove
`pack_dir` from `~/.config/atomfield/agent.toml` to go back to
releases.

## If the login node reboots

Nothing restarts the agent by itself after a reboot. When the web app
shows the cluster offline, log in and run `~/atomfield/agent start`
again. Nothing is lost meanwhile:

- Slurm keeps your jobs running without the agent.
- New jobs wait in AtomField's queue for your cluster.
- The new agent takes over the jobs that were running and reports
  them as they finish.

AtomField waits **24 hours** for a silent cluster agent before trying
its jobs again, so a night-long outage costs no work.

## Your results

Each run gets a folder in your work folder, one sub-folder per step
of the pipeline: `~/atomfield/runs/<run>/<step>/`, holding its inputs,
outputs, logs and Slurm's batch script (`job.sbatch`).

In the web app, **Get files** shows that folder and a command to copy
it to your own computer, for example:

```bash
rsync -avz you@login.cluster.edu:/home/you/atomfield/runs/<run>/ ./run/
```

Run that on your own computer. For runs up to 1 GB you can also choose
**Make a download link**: the agent zips the folder and uploads it.

Your home folder has a quota (`lfs quota -hu $USER /home` on Lustre).
Delete old runs you no longer need.

## When something goes wrong

- **A job fails at once with "sbatch refused the job"**: the message
  is Slurm's own. Usually a missing or wrong `--account` or
  `--partition`; fix it with `~/atomfield/agent login`.
- **A job stays "Pending"**: it is waiting in Slurm's queue. Check
  with `squeue --user=$USER`.
- **A job fails with "does not match its fingerprint"**: the release
  was damaged on the way. Nothing was run; retry the job.
- **A job fails with "no scripts release"**: nothing was published
  when the run started; publish a release (see `docs/releases.md`) and
  run the pipeline again.
- **The agent stopped and its log says the API refused its token**:
  the cluster was removed in the web app. Pair it again with
  `~/atomfield/agent login --pair`, then `~/atomfield/agent start`.
- **`start` says the agent runs on another login node**: log in to
  that node to stop or restart it. If that node went down, its lock
  frees itself after 3 minutes.
- **The cluster shows offline**: `~/atomfield/agent status`, then look
  at the log it names (`~/atomfield/agent.log`).
- **`pw.x` stops with "OMPI was not built with SLURM's PMI support"**:
  the program's module did not put its own `mpirun` on the PATH, so
  the job fell back to `srun`. Find that MPI with
  `ldd $(which pw.x) | grep libmpi` and add a setup line putting its
  `bin` folder first: `export PATH=/path/to/that/mpi/bin:$PATH`.
- **"Make a download link" says the run is too big**: the server, or
  a Cloudflare tunnel in front of it (at most 100 MB per upload),
  refused the zip. Copy the folder with the rsync command instead.
