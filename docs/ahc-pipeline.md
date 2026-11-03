# The anomalous Hall conductivity pipeline

A magnetic metal pushes a current sideways even without a magnetic
field: the anomalous Hall effect. Its size, the anomalous Hall
conductivity (AHC, sigma_xy, in S/cm), comes from the Berry curvature
of the bands near the Fermi level. Computing it takes four programs
in a row, each building on the one before. The editor offers them as
one ready-made pipeline: choose **New pipeline**, then pick **Anomalous
Hall (AHC)**, or drag it onto the canvas from **Prebuilt Workflows** in
the list on the left. Like every template, it ships in the scripts
release, in afscripts' `catalog/pipelines/ahc.toml` (see
`docs/releases.md`). It
belongs to the **Wannier90** package, which holds its own SCF and NSCF
steps (with spin-orbit); the plain Quantum ESPRESSO steps are another
package (`docs/quantum-espresso.md`).

## The story of one run

1. **SCF** (`pw.x`) finds the ground state of the crystal with
   spin-orbit coupling and non-collinear magnetism, the magnetization
   starting along z. It needs fully relativistic pseudopotentials
   (the `pslibrary-rel-pbe` data pack) and leaves the charge density
   and the Fermi energy.
2. **NSCF** (`pw.x`) keeps that density fixed and computes the bands
   at every point of an unshifted k-mesh, symmetry switched off,
   because Wannier90 needs the whole mesh, not just the points
   symmetry would keep. By default it computes every occupied band
   plus 24 empty ones, room for the next step's windows; the template
   asks for 36 in all.
3. **Wannier** (`wannier90.x -pp`, `pw2wannier90.x`, `wannier90.x`)
   turns those bands into a small set of localized orbitals,
   Wannier functions, and from them a tight-binding model of the
   bands near the Fermi level.
4. **Berry** (`postw90.x`) interpolates that model onto a dense mesh
   (100³ by default, 25³ in the template; finer still where the
   curvature peaks) and
   sums the Berry curvature into the AHC, at every Fermi energy from
   2 eV below to 2 eV above the SCF's.

Each step finds what it needs in the folder of the step before it
(linked under `upstream/`), through a small file that step leaves
behind, `handoff.json`: the structure, the settings, the Fermi
energy, and where its results are. So the NSCF uses exactly the
SCF's cutoffs and magnetization, and the last step still knows the
first step's Fermi energy. A file a step changes is copied (the NSCF
writes into the SCF results it reads); a file it only reads is
linked, so big files are not stored twice.

## Running it

That template opens with primitive bcc Fe, cube axes along x, y and z, so
the magnetization along z points along [001] and sigma_xy is the value
usually quoted. Replace the structure with your own (a `.cif`, or a `pw.x`
input like the template's, which keeps the cell's orientation). Choose your
cluster under **Run on** and press **Run**.

The cluster must offer four programs through the agent's setup
lines: `pw.x` and `pw2wannier90.x` (Quantum ESPRESSO) and
`wannier90.x` and `postw90.x` (Wannier90 3.x). To see what your
cluster has, on its login node:

```bash
module avail wannier90
```

```bash
module load quantum-espresso/7.2 && which pw2wannier90.x wannier90.x postw90.x
```

A program built with MPI runs under `mpirun` on the task's processes;
one built without MPI runs once, on one process (running it many
times would only repeat the work).

## A quick example, not a converged one

The template follows Wannier90's own iron tutorial (its example 18),
so a first run finishes in reasonable time:

| Step | Template | Step's own default |
|---|---|---|
| SCF k-mesh | 10×10×10 | 8×8×8 |
| NSCF k-mesh | 8×8×8 (512 points) | 10×10×10 |
| NSCF bands | 36 | occupied + 24 (40 for Fe) |
| Berry mesh | 25×25×25, refined 5×5×5 at peaks | 100×100×100 |

The tutorial's iron has 8 valence electrons and 28 bands; pslibrary's
has 16 (3s and 3p too), so 36 keeps the same 20 empty bands. The
tutorial says itself that 25³ does not converge the AHC: for a number
to quote, raise the Berry mesh as described below, and the NSCF mesh
if the Wannier spreads stay large.

## Every setting in the form

Every value the steps write into the programs' inputs is a setting in
the step's window, with its default filled in. Those decided when the
step runs say what decides them (the cutoffs: from the
pseudopotentials). How tightly each part converges is under
**Advanced**:

- SCF: convergence (1e-8 Ry), mixing (0.7), most iterations (100);
- NSCF: convergence of the bands (1e-10 Ry);
- Wannier: localization and window convergence (1e-10 Å² each),
  window mixing (0.5); and **Guiding centres**, off by default,
  under Projections.

Only names of files and folders, program paths, and what the method
needs fixed (no symmetry in the NSCF, spinor Wannier functions, the
written Hamiltonian) are not settings. **Reset** puts every setting
back: to the template's values for a step that came from it, to the
task's defaults for one you added.

## The defaults, and why

- **Projections.** Each element's default comes from a table in
  afscripts (`wannier_core.DEFAULT_PROJECTIONS`). Fe uses sp3d2
  hybrids plus the three t2g d orbitals, 9 orbitals per atom, each
  twice with spin: 18 Wannier functions. Fe's s band crosses its d
  bands near the Fermi level, so d orbitals alone (10 functions)
  cannot describe them. Another element needs **Orbitals per element**,
  e.g. `Fe: d, O: p`.
- **Windows** (eV from the Fermi energy). The frozen window, -6 to
  +2, holds bands the model reproduces exactly; the outer window,
  from -10 up, holds the bands the Wannier functions are made from.
  It has no top by default: Fe's 18 functions need bands up to some
  20 eV above the Fermi level at some k-points. A top of +8 would
  stop Wannier90 there. Before Wannier90 runs, the step checks the
  windows against the bands at every k-point and names the flag to
  change.
- **Fermi scan.** postw90's keywords are `fermi_energy_min`,
  `fermi_energy_max` and `fermi_energy_step` (0.01 eV); its output is
  `<prefix>-ahc-fermiscan.dat`. Columns: energy, then sigma_yz,
  sigma_zx and sigma_xy in S/cm.

## Reading the results

Double-click a step to see its plots and text files. The SCF's **Plots**
tab shows its convergence, the Wannier step's the spread of each
function, and the Berry step's the AHC across the scan: sigma_xy shows,
and the legend switches on the other two.

- `ahc_berry_results.csv`: sigma_xy, sigma_yz and sigma_zx at the
  Fermi energy. For bcc Fe magnetized along [001] only sigma_xy is
  large; published calculations give about 750 to 1000 S/cm.
- `ahc_calc-ahc-fermiscan.dat`: the AHC across the scan, to see how
  sensitive it is to the Fermi level.
- `ahc_wannier_summary.txt`: the windows and the Wannier functions'
  spreads. Spreads of 1 to 3 Å² each mean well-localized functions;
  far larger ones mean the projections or windows need another look.

To check convergence, connect several Berry steps to the one Wannier
step, each with a different k-point mesh (80, 120 and 160 per side): the
expensive steps run once, and the AHC should settle as the mesh
grows.

## When it stops

- *No results of a scf step upstream*: the step is not connected to
  the step before it, or that step failed.
- *the outer window holds N bands, fewer than ...*: raise the outer
  window's top (or empty it), or compute more with the NSCF's **Bands to
  compute**.
- *the frozen window holds N bands, more than ...*: narrow the frozen
  window, or project on more orbitals.
- *Wannier90 stopped with an error*: the text comes from Wannier90's
  `.werr` file; an *unrecognised keyword* there usually means
  Wannier90 2.x, which lacks `dis_froz_min`. Use Wannier90 3.x.
- *Line N of ahc_calc.eig is not 'band k-point energy'*: the band
  energies file was cut short, which usually means `pw2wannier90.x`
  ran out of disk or memory while writing. Check both where the job
  ran; a smaller NSCF mesh or fewer bands shrinks the step's files.
