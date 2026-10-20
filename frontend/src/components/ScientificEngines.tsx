export interface ScientificPackage {
  id: string;
  name: string;
  logo: string;
}

export const SCIENTIFIC_PACKAGES: ScientificPackage[] = [
  {
    id: 'quantum-espresso',
    name: 'Quantum ESPRESSO',
    logo: '/logos/quantum_espresso.png',
  },
  {
    id: 'xtb',
    name: 'xTB / GFN-FF',
    logo: '/logos/xtb.svg',
  },
  {
    id: 'mace',
    name: 'MACE',
    logo: '/logos/mace.png',
  },
  {
    id: 'sevennet',
    name: 'SevenNet',
    logo: '/logos/sevennet.png',
  },
  {
    id: 'chgnet',
    name: 'CHGNet',
    logo: '/logos/chgnet.png',
  },
  {
    id: 'ase',
    name: 'ASE',
    logo: '/logos/ase.png',
  },
  {
    id: 'rdkit',
    name: 'RDKit',
    logo: '/logos/rdkit.png',
  },
  {
    id: 'sella',
    name: 'Sella',
    logo: '/logos/sella.png',
  },
  {
    id: 'orca',
    name: 'ORCA',
    logo: '/logos/orca.png',
  },
];

export default function ScientificEngines() {
  return (
    <section className="w-full px-6 py-16 sm:py-20 my-6 sm:my-10">
      <div className="max-w-6xl mx-auto flex flex-col items-center text-center">
        {/* Simple Centered Heading */}
        <h3 className="text-xs sm:text-sm font-semibold tracking-wider text-slate-500 uppercase mb-10 sm:mb-12">
          Core Scientific Packages
        </h3>

        {/* Center-Justified Plain Logo Grid (No Bounding Boxes) */}
        <div className="flex flex-wrap items-center justify-center gap-10 sm:gap-14 md:gap-16">
          {SCIENTIFIC_PACKAGES.map((pkg) => (
            <div
              key={pkg.id}
              className="flex flex-col items-center justify-center gap-2.5"
            >
              <div className="h-20 sm:h-24 w-36 sm:w-44 flex items-center justify-center">
                <img
                  src={pkg.logo}
                  alt={pkg.name}
                  className="max-h-20 sm:max-h-24 max-w-full object-contain"
                  loading="lazy"
                />
              </div>
              <span className="text-xs sm:text-sm font-semibold text-slate-700">
                {pkg.name}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
