import {
  SECTION_HEAD,
  SECTION_SIDES,
  SECTION_TEXT,
  SECTION_TITLE,
  SECTION_WIDTH,
} from './landingStyle';

export interface ScientificPackage {
  id: string;
  name: string;
  logo: string;
  // What it does, in a few words.
  role: string;
  // Its official site.
  url: string;
}

export const SCIENTIFIC_PACKAGES: ScientificPackage[] = [
  {
    id: 'quantum-espresso',
    name: 'Quantum ESPRESSO',
    logo: '/logos/quantum_espresso.png',
    role: 'Plane-wave DFT',
    url: 'https://www.quantum-espresso.org/',
  },
  {
    id: 'wannier90',
    name: 'Wannier90',
    logo: '/logos/wannier90.png',
    role: 'Wannier functions',
    url: 'https://wannier.org/',
  },
  {
    id: 'xtb',
    name: 'xTB / GFN-FF',
    logo: '/logos/xtb.svg',
    role: 'Semi-empirical quantum chemistry',
    url: 'https://github.com/grimme-lab/xtb',
  },
  {
    id: 'orca',
    name: 'ORCA',
    logo: '/logos/orca.png',
    role: 'Molecular quantum chemistry',
    url: 'https://www.faccts.de/orca/',
  },
  {
    id: 'lammps',
    name: 'LAMMPS',
    logo: '/logos/lammps.png',
    role: 'Classical molecular dynamics',
    url: 'https://www.lammps.org/',
  },
  {
    id: 'ase',
    name: 'ASE',
    logo: '/logos/ase.png',
    role: 'Atomistic simulation toolkit',
    url: 'https://wiki.fysik.dtu.dk/ase/',
  },
  {
    id: 'mace',
    name: 'MACE',
    logo: '/logos/mace.png',
    role: 'Machine-learned potentials',
    url: 'https://github.com/ACEsuit/mace',
  },
  {
    id: 'sevennet',
    name: 'SevenNet',
    logo: '/logos/sevennet.png',
    role: 'Machine-learned potentials',
    url: 'https://github.com/MDIL-SNU/SevenNet',
  },
  {
    id: 'chgnet',
    name: 'CHGNet',
    logo: '/logos/chgnet.png',
    role: 'Machine-learned potentials',
    url: 'https://github.com/CederGroupHub/chgnet',
  },
  {
    id: 'rdkit',
    name: 'RDKit',
    logo: '/logos/rdkit.png',
    role: 'Cheminformatics',
    url: 'https://www.rdkit.org/',
  },
  {
    id: 'sella',
    name: 'Sella',
    logo: '/logos/sella.png',
    role: 'Transition-state search',
    url: 'https://github.com/zadorlab/sella',
  },
];

// The same gap as the cards above: two, three, four or six across, and a
// last row with fewer in the middle.
const TILE_ROW = 'flex flex-wrap justify-center gap-8';
const TILE = [
  'group flex flex-col items-center p-5 text-center bg-white rounded-2xl',
  'border border-slate-200/90 shadow-xs hover:border-orange-500',
  'hover:shadow-card-lift transition-all duration-300 ease-out',
  'w-[calc((100%-2rem)/2)] sm:w-[calc((100%-4rem)/3)]',
  'lg:w-[calc((100%-6rem)/4)] xl:w-[calc((100%-10rem)/6)]',
].join(' ');
const LOGO_BOX = 'flex items-center justify-center w-full h-16 mb-3';
const LOGO = 'max-h-16 max-w-full object-contain';
const NAME = [
  'text-sm font-semibold text-slate-800 group-hover:text-orange-600',
  'transition-colors',
].join(' ');
const ROLE = 'mt-1 text-xs leading-snug text-slate-500';

export default function ScientificEngines() {
  return (
    <section className={`${SECTION_SIDES} pt-8 pb-16`}>
      <div className={SECTION_WIDTH}>
        <div className={SECTION_HEAD}>
          <h2 className={SECTION_TITLE}>The packages behind the workflows</h2>
          <p className={SECTION_TEXT}>
            These programs do the science, in today's workflows and the ones in
            development. They run on your own machines, and every step shows
            you their inputs, logs and outputs.
          </p>
        </div>

        <div className={TILE_ROW}>
          {SCIENTIFIC_PACKAGES.map((pkg) => (
            <a
              key={pkg.id}
              href={pkg.url}
              target="_blank"
              rel="noreferrer"
              className={TILE}
            >
              <div className={LOGO_BOX}>
                <img
                  src={pkg.logo}
                  alt=""
                  className={LOGO}
                  loading="lazy"
                />
              </div>
              <span className={NAME}>{pkg.name}</span>
              <span className={ROLE}>{pkg.role}</span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
