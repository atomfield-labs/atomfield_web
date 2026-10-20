export interface ScientificPackage {
  id: string;
  name: string;
  role: string;
  logo: string;
  website?: string;
}

export const SCIENTIFIC_PACKAGES: ScientificPackage[] = [
  {
    id: 'quantum-espresso',
    name: 'Quantum ESPRESSO',
    role: 'Plane-Wave DFT & Phonons',
    logo: '/logos/quantum_espresso.png',
    website: 'https://www.quantum-espresso.org',
  },
  {
    id: 'xtb',
    name: 'xTB / GFN-FF',
    role: 'Semi-Empirical QM & Dynamics',
    logo: '/logos/xtb.svg',
    website: 'https://github.com/grimme-lab/xtb',
  },
  {
    id: 'mace',
    name: 'MACE',
    role: 'Equivariant ML Potentials',
    logo: '/logos/mace.png',
    website: 'https://github.com/ACEsuit/mace',
  },
  {
    id: 'sevennet',
    name: 'SevenNet',
    role: 'Foundation Interatomic MLFF',
    logo: '/logos/sevennet.png',
    website: 'https://github.com/MDIL-SNU/SevenNet',
  },
  {
    id: 'chgnet',
    name: 'CHGNet',
    role: 'Universal Crystal MLFF',
    logo: '/logos/chgnet.png',
    website: 'https://github.com/CederGroupHub/chgnet',
  },
  {
    id: 'ase',
    name: 'ASE',
    role: 'Simulation & Trajectories',
    logo: '/logos/ase.png',
    website: 'https://wiki.fysik.dtu.dk/ase/',
  },
  {
    id: 'rdkit',
    name: 'RDKit',
    role: 'Cheminformatics & Graph Models',
    logo: '/logos/rdkit.png',
    website: 'https://www.rdkit.org',
  },
  {
    id: 'sella',
    name: 'Sella',
    role: 'Saddle Point & TS Optimization',
    logo: '/logos/sella.png',
    website: 'https://github.com/zadorlab/sella',
  },
  {
    id: 'orca',
    name: 'ORCA',
    role: 'Ab Initio Quantum Chemistry',
    logo: '/logos/orca.png',
    website: 'https://www.faccts.de/orca/',
  },
];

export default function ScientificEngines() {
  return (
    <section className="w-full px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 py-12 border-t border-slate-200/80 bg-slate-50/60">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <div className="mb-6 text-center md:text-left">
          <p className="text-[11px] font-mono font-bold tracking-widest text-orange-600 uppercase">
            First-Principles &amp; ML Foundation
          </p>
          <h3 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight mt-1">
            Integrated Scientific Packages &amp; Foundation Models
          </h3>
          <p className="text-xs text-slate-600 font-medium mt-1">
            Directly orchestrates vetted quantum chemistry codes, electronic structure packages, and ML interatomic potentials.
          </p>
        </div>

        {/* Official Logos Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3.5 sm:gap-4">
          {SCIENTIFIC_PACKAGES.map((pkg) => (
            <div
              key={pkg.id}
              className="bg-white rounded-xl border border-slate-200/90 p-4 flex flex-col justify-between hover:border-orange-500 hover:shadow-sm transition-all duration-200 group"
            >
              {/* Logo Frame */}
              <div className="w-full h-14 flex items-center justify-center mb-3">
                <img
                  src={pkg.logo}
                  alt={`${pkg.name} logo`}
                  className="max-h-12 max-w-full object-contain group-hover:scale-105 transition-transform duration-200"
                  loading="lazy"
                />
              </div>

              {/* Title & Role */}
              <div className="pt-2 border-t border-slate-100 text-center">
                <h4 className="text-xs font-bold text-slate-900 truncate group-hover:text-orange-600 transition-colors">
                  {pkg.name}
                </h4>
                <p className="text-[10.5px] font-mono text-orange-700 font-medium truncate mt-0.5">
                  {pkg.role}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
