# Labs, roles and workflows

Who can use AtomField, and which scripts each person sees and runs.

A **workflow** is a named bundle of tasks and ready-made pipelines, and
is what a lab is given. There are three roles:

| | Owner | Admin | User |
|---|---|---|---|
| Sees and runs | everything | all their lab's | what is ticked |
| A lab's workflows | ticks, any lab | reads | |
| People | any lab; makes admins | adds, ticks, removes | |
| Quotas, releases | yes | | |

The server enforces this for the web app and for script keys alike: a
task outside someone's workflows is refused like a task that does not
exist. Each person sees only their own sessions.

## Setting up a lab

1. Put the owner's address in `OWNER_EMAILS` in `.env` and restart. It
   must be the address Google gives for that account.
2. As the owner, open **Labs**, choose **New lab**, and enter its name
   and its admin's email.
3. On the lab's page, tick the workflows it may use.
4. The admin signs in, opens **Lab**, and adds people by email. They
   start with nothing ticked; the admin ticks workflows for each.

Only the owner's address and addresses on a lab's list can sign in at
all. While the app is in Testing on Google's side, each person must also
be a test user there, or Google stops them first.

## If someone is refused

The sign-in page names the address Google gave. That is the one to add:
one institute's accounts can carry several addresses, and a person on
the list under another one is not recognized. Until someone signs in,
the lab's page says "Not signed in yet" beside them.

## Taking access away

- Unticking a workflow on a lab's page stops everyone in that lab from
  seeing or starting it at once. Ticking it again restores what each
  person had.
- Removing someone from a lab signs them out and stops their keys. Their
  runs stay, and another lab can add them later.
- Runs already started finish either way.

## Adding or changing a workflow

Workflows live in afscripts, in `catalog/workflows/<id>.toml`:

```toml
id = "quantum_espresso"
title = "Quantum ESPRESSO"
description = "What it does."
tasks = ["ahc_scf", "ahc_nscf"]
pipelines = ["ahc"]
```

A task may be in several workflows. Every task and pipeline must be in at
least one, and a pipeline's tasks must all be in its workflow, or the
export stops. Export the catalog from the AtomField folder (the scripts
need these packages just to describe their options):

```bash
PYTHONPATH=scripts_repo/src uv run --python 3.11 \
  --with ase --with rdkit --with networkx --with sella \
  python -m afscripts.catalog -output scripts_repo/catalog.json
```

Then commit it in afscripts and publish a release (see `releases.md`).
Until a release has workflows, only the owner sees anything.
