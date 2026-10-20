import React from 'react'

export interface ScientificEngine {
  id: string;
  name: string;
  role: string;
  category: 'Electronic Structure' | 'Semi-Empirical' | 'Machine Learning Force Field' | 'Simulation Core' | 'Reaction Dynamics';
  description: string;
  accentColor: string;
  renderLogo: () => React.ReactNode;
}

export const SCIENTIFIC_ENGINES: ScientificEngine[] = [
  {
    id: 'quantum-espresso',
    name: 'Quantum ESPRESSO',
    role: 'Plane-Wave DFT & Phonons',
    category: 'Electronic Structure',
    description: 'Ab initio plane-wave pseudopotential density functional theory and periodic lattice dynamics.',
    accentColor: '#b91c1c',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Atomic Espresso Cup & Swirling Quantum Orbitals */}
        <path
          d="M10 20C10 30 18 36 28 36C38 36 42 28 42 20H10Z"
          fill="#b91c1c"
          fillOpacity="0.12"
          stroke="#b91c1c"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M38 23C42 23 44 21 44 18C44 15 41 14 38 15"
          stroke="#b91c1c"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <line x1="8" y1="40" x2="38" y2="40" stroke="#b91c1c" strokeWidth="2.5" strokeLinecap="round" />
        {/* Quantum Orbital Steam */}
        <ellipse cx="24" cy="11" rx="10" ry="3.5" stroke="#ea580c" strokeWidth="2" strokeDasharray="3 2" />
        <ellipse cx="24" cy="11" rx="4" ry="8" stroke="#b91c1c" strokeWidth="2" strokeDasharray="3 2" />
        <circle cx="24" cy="11" r="2.5" fill="#ea580c" />
      </svg>
    ),
  },
  {
    id: 'xtb',
    name: 'xTB / GFN-FF',
    role: 'Semi-Empirical Quantum Mechanics',
    category: 'Semi-Empirical',
    description: 'Extended tight-binding GFN2-xTB and generic force fields for accelerated reactive dynamics.',
    accentColor: '#0284c7',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Tight-Binding Overlapping Orbital Lobes */}
        <circle cx="17" cy="24" r="11" stroke="#0284c7" strokeWidth="2.2" strokeDasharray="4 2" fill="#0284c7" fillOpacity="0.1" />
        <circle cx="31" cy="24" r="11" stroke="#0ea5e9" strokeWidth="2.2" strokeDasharray="4 2" fill="#0ea5e9" fillOpacity="0.1" />
        {/* Core Nuclei and Bond Resonance */}
        <path d="M17 24L31 24" stroke="#0369a1" strokeWidth="3" strokeLinecap="round" />
        <circle cx="17" cy="24" r="4.5" fill="#0284c7" />
        <circle cx="31" cy="24" r="4.5" fill="#0ea5e9" />
        <path d="M24 16L24 32" stroke="#f97316" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'mace',
    name: 'MACE',
    role: 'Equivariant Neural Potentials',
    category: 'Machine Learning Force Field',
    description: 'Higher-order equivariant graph neural networks delivering DFT-accuracy at linear MD scaling.',
    accentColor: '#059669',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Higher-order Equivariant Message Passing Graph */}
        <path d="M24 6L40 16V34L24 44L8 34V16L24 6Z" stroke="#059669" strokeWidth="2" strokeLinejoin="round" fill="#059669" fillOpacity="0.08" />
        <line x1="24" y1="6" x2="24" y2="44" stroke="#059669" strokeWidth="1.5" strokeOpacity="0.5" />
        <line x1="8" y1="16" x2="40" y2="34" stroke="#059669" strokeWidth="1.5" strokeOpacity="0.5" />
        <line x1="8" y1="34" x2="40" y2="16" stroke="#059669" strokeWidth="1.5" strokeOpacity="0.5" />
        {/* Central Invariant Atom */}
        <circle cx="24" cy="24" r="5" fill="#10b981" />
        <circle cx="24" cy="6" r="3" fill="#059669" />
        <circle cx="40" cy="16" r="3" fill="#059669" />
        <circle cx="40" cy="34" r="3" fill="#059669" />
        <circle cx="24" cy="44" r="3" fill="#059669" />
        <circle cx="8" cy="34" r="3" fill="#059669" />
        <circle cx="8" cy="16" r="3" fill="#059669" />
      </svg>
    ),
  },
  {
    id: 'sevennet',
    name: 'SevenNet',
    role: 'Foundation Interatomic Potential',
    category: 'Machine Learning Force Field',
    description: 'Equilibrium & non-equilibrium foundation potential trained on diverse chemical trajectories.',
    accentColor: '#6366f1',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Stylized Atomic Numeral 7 with Neural Nodes */}
        <path d="M12 12H36L22 38" stroke="#6366f1" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M18 25H32" stroke="#818cf8" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="12" cy="12" r="4.5" fill="#4f46e5" />
        <circle cx="36" cy="12" r="4.5" fill="#6366f1" />
        <circle cx="22" cy="38" r="4.5" fill="#4338ca" />
        <circle cx="32" cy="25" r="3" fill="#f97316" />
      </svg>
    ),
  },
  {
    id: 'ase',
    name: 'ASE',
    role: 'Atomic Simulation Environment',
    category: 'Simulation Core',
    description: 'Standard Python atomistic simulation architecture, trajectory I/O, and optimizer drivers.',
    accentColor: '#15803d',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Iconic Tri-orbital Atomic Simulation Shells */}
        <ellipse cx="24" cy="24" rx="19" ry="7" transform="rotate(-30 24 24)" stroke="#15803d" strokeWidth="2" />
        <ellipse cx="24" cy="24" rx="19" ry="7" transform="rotate(30 24 24)" stroke="#16a34a" strokeWidth="2" />
        <ellipse cx="24" cy="24" rx="19" ry="7" transform="rotate(90 24 24)" stroke="#22c55e" strokeWidth="2" />
        <circle cx="24" cy="24" r="5" fill="#15803d" />
        <circle cx="39" cy="15" r="2.5" fill="#ea580c" />
        <circle cx="9" cy="33" r="2.5" fill="#0284c7" />
      </svg>
    ),
  },
  {
    id: 'rdkit',
    name: 'RDKit',
    role: 'Cheminformatics & Graph Representations',
    category: 'Simulation Core',
    description: 'SMILES parsing, molecular topology, 3D conformer generation, and chemical sanity filtering.',
    accentColor: '#2563eb',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Aromatic Benzene Graph Structure */}
        <polygon points="24,8 38,16 38,32 24,40 10,32 10,16" stroke="#2563eb" strokeWidth="2.5" fill="#2563eb" fillOpacity="0.08" />
        <circle cx="24" cy="24" r="8" stroke="#3b82f6" strokeWidth="2" strokeDasharray="3 3" />
        <circle cx="24" cy="8" r="3.5" fill="#2563eb" />
        <circle cx="38" cy="16" r="3.5" fill="#2563eb" />
        <circle cx="38" cy="32" r="3.5" fill="#2563eb" />
        <circle cx="24" cy="40" r="3.5" fill="#2563eb" />
        <circle cx="10" cy="32" r="3.5" fill="#2563eb" />
        <circle cx="10" cy="16" r="3.5" fill="#2563eb" />
      </svg>
    ),
  },
  {
    id: 'sella',
    name: 'Sella',
    role: 'Saddle Point & TS Search',
    category: 'Reaction Dynamics',
    description: 'First-order saddle point optimization algorithm to rigorously locate chemical transition states.',
    accentColor: '#ea580c',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Hyperbolic Paraboloid Saddle Curve */}
        <path d="M8 36C16 16 32 16 40 36" stroke="#ea580c" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M12 14C20 30 28 30 36 14" stroke="#f97316" strokeWidth="2" strokeLinecap="round" strokeDasharray="4 2" />
        {/* Transition State Critical Point */}
        <circle cx="24" cy="22" r="4.5" fill="#ea580c" />
        <path d="M24 14V30" stroke="#c2410c" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M16 22H32" stroke="#c2410c" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'chgnet',
    name: 'CHGNet',
    role: 'Crystal Graph Pretrained Potential',
    category: 'Machine Learning Force Field',
    description: 'Universal charge-informed neural network potential for inorganic crystal relaxation and ions.',
    accentColor: '#0891b2',
    renderLogo: () => (
      <svg className="w-9 h-9" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Periodic Crystal Unit Cell Wireframe with Charge Valence */}
        <rect x="12" y="12" width="24" height="24" rx="2" stroke="#0891b2" strokeWidth="2" fill="#0891b2" fillOpacity="0.08" />
        <path d="M12 12L20 6H40V26L36 36" stroke="#06b6d4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="36" y1="12" x2="40" y2="6" stroke="#06b6d4" strokeWidth="1.5" />
        <circle cx="12" cy="12" r="3" fill="#0891b2" />
        <circle cx="36" cy="12" r="3" fill="#0891b2" />
        <circle cx="36" cy="36" r="3" fill="#0891b2" />
        <circle cx="12" cy="36" r="3" fill="#0891b2" />
        <circle cx="24" cy="24" r="4.5" fill="#f97316" />
      </svg>
    ),
  },
]

export default function ScientificEngines() {
  return (
    <section className="w-full px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 py-16 border-t border-slate-200/70 bg-gradient-to-b from-slate-50 via-white to-slate-50">
      <div className="max-w-7xl mx-auto">
        {/* Header Kicker */}
        <div className="mb-8 text-center md:text-left">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="h-px w-6 bg-orange-500" />
            <span className="text-[11px] font-mono font-bold tracking-widest text-orange-600 uppercase">
              First-Principles &amp; ML Foundation
            </span>
          </div>
          <h3 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Scientific Packages &amp; Foundation Models
          </h3>
          <p className="text-xs sm:text-sm text-slate-600 font-medium mt-1.5 max-w-2xl">
            Calculations are executed through vetted quantum electronic structure engines, semi-empirical codes, and state-of-the-art equivariant interatomic potentials.
          </p>
        </div>

        {/* Responsive Grid of Scientific Packages */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {SCIENTIFIC_ENGINES.map((engine) => (
            <div
              key={engine.id}
              className="bg-white rounded-xl border border-slate-200/90 p-4.5 flex flex-col justify-between hover:border-orange-500 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 group"
            >
              <div>
                {/* Logo and Name Header */}
                <div className="flex items-center gap-3.5 mb-3">
                  <div className="p-1.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform duration-200">
                    {engine.renderLogo()}
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-sm font-bold text-slate-900 truncate group-hover:text-orange-600 transition-colors">
                      {engine.name}
                    </h4>
                    <p className="text-[11px] font-mono text-orange-700 font-semibold truncate">
                      {engine.role}
                    </p>
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs text-slate-600 font-normal leading-relaxed line-clamp-2">
                  {engine.description}
                </p>
              </div>

              {/* Category Pill Tag */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wide">
                  {engine.category}
                </span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" title="Active Engine" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
