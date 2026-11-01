# Quantum ESPRESSO: bands, density of states and phonons

The Quantum ESPRESSO package has four steps and three ready-made
pipelines (**Prebuilt Pipelines → Silicon bands, Silicon density of
states, Silicon phonons**). A lab is given the package as a whole on
the Labs page (see `docs/labs.md`). The scripts are afscripts'
`qe_*_driver.py`; the steps and pipelines are described in its
`catalog/` and ship in the scripts release (see `docs/releases.md`).

## The story of one run

1. **SCF** (`pw.x`) finds the ground state of the crystal: the electron
   density, the Fermi energy and the total energy. It is the one step
   that takes the structure and the physics: cutoffs, the k-mesh, how
   electrons fill the bands (smearing for metals, fixed for
   insulators), a starting magnetization if the crystal is magnetic.
2. **Bands** (`pw.x`, `bands.x`) keeps that density fixed and computes
   the bands at every point of a path through the Brillouin zone. It
   says whether there is a gap, how big, and whether it is direct.
3. **Density of states** (`pw.x`, `dos.x`, optionally `projwfc.x`)
   computes the bands on a denser mesh and counts the states at each
   energy by the optimized tetrahedron method. **Project on orbitals**
   also splits the count by atom and orbital.
4. **Phonons** (`ph.x`, `q2r.x`, `matdyn.x`) finds how the crystal
   vibrates: the dynamical matrices on a coarse q-mesh, turned into
   forces between atoms, then the frequencies along a path and on a
   fine mesh. It says whether any mode is imaginary.

Steps 2 to 4 find what they need in the SCF's folder (linked under
`upstream/`), through its `handoff.json`: the structure, the settings,
the electrons, and where its results are. So they repeat the SCF's
cutoffs, smearing and spin exactly, and cannot disagree with it. A
step copies the SCF's results folder and never changes the original;
only the phonon step also copies the wavefunctions, which `ph.x` needs.

## What each step leaves

Double-click a finished step to see what it left. Its **Plots** tab
draws these in the browser: hover to read values, drag to zoom,
double-click to reset, click a legend entry to hide a curve, and the
camera icon saves a PNG.

| Step | Plots |
|---|---|
| SCF | how the accuracy fell, iteration by iteration |
| Bands | the band structure, one colour per spin |
| Density of states | the density; projected, by element and orbital |
| Phonons | the dispersion beside the phonon density of states |

Its **Artifacts** tab shows its text files, the summary first: the
input deck, the program's output and the tables. Every step writes
`<job>_summary.txt`, a few lines a person reads, and:

| Step | Files |
|---|---|
| Bands | `_bands.dat` (table), `_bands.json` |
| Density of states | `_dos.dat`, `_dos.json`; projected, `_pdos.dat` |
| Phonons | `_dispersion.dat`, `_phdos.dat`, `_phonons.json`, `.fc` |

The tables and the JSON hold the same numbers, for gnuplot or your own
plots. A plot holds at most 2,000 points per curve; the tables keep them
all. Files too big to show here stay on the cluster (**Get files**).

## Where zero is

Energies are in eV from **zero**: the top of the valence band if the
material has a gap, the Fermi energy if it is a metal. Bands and the
density of states use the same zero, so their plots line up. The
summary says which it is (`zero_at`).

The gap is found along the path only: the true gap is this one only
if the path passes through the band edges. For silicon the standard
path does.

## The defaults, and why

- **Cutoffs** are the largest the pseudopotentials suggest, rounded up
  to whole Ry. Fill them in to choose.
- **k-mesh** 8×8×8, a reasonable start for a small cell. The density of
  states uses 12×12×12.
- **Filling** is smearing by default (the safe choice for any
  material). The silicon pipelines set `fixed`, since silicon has a gap.
- **Bands computed**: the filled ones plus 8 empty ones for the band
  structure, plus 10 for the density of states, so the window above
  the gap is complete. The density of states warns if its bands stop
  below the top of its window.
- **Phonons** need the SCF converged much more tightly than usual
  (**Convergence**, under Advanced, of 1e-10 or less; the silicon
  pipeline sets 1e-12), and a k-mesh the q-mesh divides: 4×4×4 on 8×8×8.
  The step stops if it does not, and warns if the SCF was too loose. A
  mode counts as imaginary below -5 cm^-1; smaller negative values are
  noise from the acoustic sum rule, `crystal` by default.

## What to check on your own system

The scripts were tried on silicon with Quantum ESPRESSO 7.2: the
inputs run, the outputs are read, silicon's gap is indirect, its
acoustic modes vanish at Gamma, and none of its modes is imaginary.
That checks the plumbing. Whether a calculation is **converged** for
your crystal is for you to judge: raise the cutoffs, the k-mesh and
the q-mesh until the result stops moving.

## What it does not do

- **Spin-orbit** is not offered here: it needs fully relativistic
  pseudopotentials, which this package's pack does not hold. The
  Wannier90 package's SCF does spin-orbit, with its own pack.
- **Phonons with spin** (a magnetic crystal, or spin-orbit) are
  refused.
- **Polar crystals** get no splitting of the optical modes at Gamma
  (LO-TO), since no dielectric constant or effective charges are
  computed.
- **Other elements** than silicon need a bigger pseudopotential pack.
  The pack `pslibrary-pbe 1.0.0-si` holds silicon only (the PAW file
  `Si.pbe-n-kjpaw_psl.1.0.0.UPF`, scalar relativistic). To add elements,
  put their files in a folder with silicon's, publish it as a new
  version (`docs/releases.md`, "Data packs"), add them to afscripts'
  `utilities/pseudopotentials.toml`, and name the new version in the
  four tasks' `[[data]]` tables.

## Running it on a cluster

The cluster must offer seven programs through the agent's setup lines,
all of them part of Quantum ESPRESSO: `pw.x`, `bands.x`, `dos.x`,
`projwfc.x`, `ph.x`, `q2r.x` and `matdyn.x`. To see what your cluster
has, on its login node:

```bash
module avail quantum-espresso
```

```bash
module load quantum-espresso/7.2 && which pw.x ph.x matdyn.x
```

A program built with MPI runs under `mpirun` on the task's processes.
`q2r.x`, `matdyn.x`, `bands.x`, `dos.x` and `projwfc.x` do little work
and run on one process; `pw.x` and `ph.x` take all of them. `ph.x` is
the long one: its time grows with the number of q-points and the size
of the cell, so the phonon task asks for 12 hours by default.

## Testing it

afscripts' tests run every step without Quantum ESPRESSO, on real
outputs trimmed to a few rows. `tests/test_qe_real.py` runs silicon
through all four steps with the real programs, in about a minute; it
is skipped where they are missing. To run it, in an environment with
Quantum ESPRESSO and `ESPRESSO_PSEUDO` pointing at a folder with the
silicon file:

```bash
python -m pytest tests/test_qe_real.py
```
