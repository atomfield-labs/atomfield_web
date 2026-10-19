import { Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import PESTerrain from '../animations/PESTerrain'
import JablonskiDiagram from '../animations/JablonskiDiagram'
import IonLattice from '../animations/IonLattice'
import PolymerMelt from '../animations/PolymerMelt'

export default function SectionsContainer() {
  return (
    <section id="modules-grid" className="w-full px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 pb-24">
      {/* Section Header */}
      <div className="mb-10 text-center md:text-left max-w-2xl">
        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
          Calculation Modules
        </h2>
        <p className="text-base text-slate-600 mt-2 font-medium">
          Preconfigured high-throughput quantum and molecular simulation workflows.
        </p>
      </div>

      {/* 3-Cards Per Row Responsive Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8 w-full">
        {/* Card 1: Nanoreactor (First) */}
        <div 
          onClick={() => window.location.hash = '#pipeline/nanoreactor'}
          className="bg-white/95 backdrop-blur-xl rounded-2xl border border-blue-500/30 shadow-md hover:shadow-xl hover:border-blue-500 transition-all duration-300 flex flex-col overflow-hidden cursor-pointer group"
        >
          <div className="w-full h-52 bg-slate-950 relative overflow-hidden rounded-t-2xl">
            <Suspense fallback={<div className="w-full h-full bg-slate-900 animate-pulse" />}>
              <Canvas camera={{ position: [0, 2.5, 7], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 15, 10]} intensity={2.0} color="#ffffff" />
                <directionalLight position={[-10, 10, -5]} intensity={1.2} color="#93c5fd" />
                <pointLight position={[0, -2, 3]} intensity={0.8} color="#f97316" />
                <PESTerrain />
              </Canvas>
            </Suspense>
            <div className="absolute top-3 right-3 px-2.5 py-1 text-[11px] font-bold tracking-wider rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/40 backdrop-blur-md">
              LIVE DEMO
            </div>
          </div>
          <div className="p-6 flex flex-col flex-grow justify-between">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-blue-600 transition-colors">
                Nanoreactor & Catalysis
              </h3>
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wider mt-1">
                Reaction Networks & Transition State Search
              </p>
              <p className="text-sm text-slate-600 font-medium leading-relaxed mt-3">
                Discover reaction pathways and compute activation barriers ($E_a$) in accelerated reactive molecular environments with xTB and GFN-FF.
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.location.hash = '#pipeline/nanoreactor';
              }}
              className="w-full mt-6 py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold tracking-wide rounded-xl transition-colors shadow-sm flex items-center justify-center gap-2"
            >
              Launch Nanoreactor &rarr;
            </button>
          </div>
        </div>

        {/* Card 2: Optoelectronics (Second) */}
        <div className="bg-white/95 backdrop-blur-xl rounded-2xl border border-slate-200/80 shadow-md hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          <div className="w-full h-52 bg-slate-950 relative overflow-hidden rounded-t-2xl">
            <Suspense fallback={<div className="w-full h-full bg-slate-900 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 7.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={2.0} color="#ffffff" />
                <JablonskiDiagram />
              </Canvas>
            </Suspense>
            {/* Crisp HTML State Overlays */}
            <div className="absolute left-3 bottom-3 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-900/80 text-slate-400 border border-slate-800 pointer-events-none">
              S₀ Ground
            </div>
            <div className="absolute left-3 top-3 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-950/80 text-sky-400 border border-sky-800/50 pointer-events-none">
              S₁ Singlet
            </div>
            <div className="absolute right-3 bottom-14 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-pink-950/80 text-pink-400 border border-pink-800/50 pointer-events-none">
              T₁ Triplet
            </div>
            <div className="absolute top-3 right-3 px-2.5 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-800/80 text-slate-400 border border-slate-700/60 backdrop-blur-md">
              COMING SOON
            </div>
          </div>
          <div className="p-6 flex flex-col flex-grow justify-between">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Optoelectronic Properties
              </h3>
              <p className="text-xs font-semibold text-orange-600 uppercase tracking-wider mt-1">
                TD-DFT Excited States & UV-Vis Spectra
              </p>
              <p className="text-sm text-slate-600 font-medium leading-relaxed mt-3">
                Calculate electronic excited states, fluorescence vs phosphorescence pathways, oscillator strengths, and frontier orbital energies directly in-browser.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: TD-DFT</span>
            </div>
          </div>
        </div>

        {/* Card 3: Solid State (Third) */}
        <div className="bg-white/95 backdrop-blur-xl rounded-2xl border border-slate-200/80 shadow-md hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          <div className="w-full h-52 bg-slate-950 relative overflow-hidden rounded-t-2xl">
            <Suspense fallback={<div className="w-full h-full bg-slate-900 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 8.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 10, 10]} intensity={2.0} color="#ffffff" />
                <IonLattice />
              </Canvas>
            </Suspense>
            <div className="absolute top-3 right-3 px-2.5 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-800/80 text-slate-400 border border-slate-700/60 backdrop-blur-md">
              COMING SOON
            </div>
          </div>
          <div className="p-6 flex flex-col flex-grow justify-between">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Solid State & Lattices
              </h3>
              <p className="text-xs font-semibold text-purple-600 uppercase tracking-wider mt-1">
                Periodic DFT & Ion Transport Dynamics
              </p>
              <p className="text-sm text-slate-600 font-medium leading-relaxed mt-3">
                Model infinite crystal structures, phonon dispersions, and interstitial ion migration pathways in solid electrolytes and battery cathode materials.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: Plane-Wave DFT</span>
            </div>
          </div>
        </div>

        {/* Card 4: Polymers (Fourth) */}
        <div className="bg-white/95 backdrop-blur-xl rounded-2xl border border-slate-200/80 shadow-md hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          <div className="w-full h-52 bg-slate-950 relative overflow-hidden rounded-t-2xl">
            <Suspense fallback={<div className="w-full h-full bg-slate-900 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 10], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={2.0} color="#ffffff" />
                <pointLight position={[0, 0, 3]} intensity={1.0} color="#ef4444" />
                <PolymerMelt />
              </Canvas>
            </Suspense>
            <div className="absolute top-3 right-3 px-2.5 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-800/80 text-slate-400 border border-slate-700/60 backdrop-blur-md">
              COMING SOON
            </div>
          </div>
          <div className="p-6 flex flex-col flex-grow justify-between">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Polymer Chain Dynamics
              </h3>
              <p className="text-xs font-semibold text-rose-600 uppercase tracking-wider mt-1">
                Chain Entanglement & Rheology
              </p>
              <p className="text-sm text-slate-600 font-medium leading-relaxed mt-3">
                Simulate macromolecular entanglement, stress-strain curves, glass transition temperatures ($T_g$), and mechanical bond scission events.
              </p>
            </div>
            <div className="mt-6 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: MD / GROMACS</span>
            </div>
          </div>
        </div>

        {/* Platform Orchestrator Card (Spanning 2 columns to complete row 2) */}
        <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 text-white rounded-2xl p-7 border border-slate-800 shadow-md flex flex-col justify-between lg:col-span-2 relative overflow-hidden">
          <div className="relative z-10">
            <div className="flex items-center justify-between mb-4">
              <span className="px-3 py-1 bg-orange-500/20 text-orange-400 border border-orange-500/30 rounded-full text-xs font-bold tracking-wider">
                CORE PLATFORM
              </span>
              <span className="text-xs font-mono text-slate-400">DAG Execution Engine</span>
            </div>
            <h3 className="text-2xl font-extrabold tracking-tight text-white mb-2">
              Modular Pipeline Orchestrator
            </h3>
            <p className="text-slate-300 text-sm leading-relaxed max-w-xl">
              The blank canvas where LLM-driven science happens. Chain geometry optimization, transition state searches, and property evaluations into executing physics pipelines.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              <span className="px-3 py-1 bg-slate-800/80 text-slate-300 rounded-lg text-xs font-medium border border-slate-700/50">Natural Language Dispatch</span>
              <span className="px-3 py-1 bg-slate-800/80 text-slate-300 rounded-lg text-xs font-medium border border-slate-700/50">Model Context Protocol</span>
              <span className="px-3 py-1 bg-slate-800/80 text-slate-300 rounded-lg text-xs font-medium border border-slate-700/50">Real-time DAG Execution</span>
            </div>
          </div>
          <div className="relative z-10 mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between">
            <span className="text-xs text-slate-400 font-mono">Ready for custom workflows</span>
            <button
              onClick={() => window.location.hash = '#pipeline/new'}
              className="px-5 py-2.5 bg-orange-600 hover:bg-orange-500 text-white font-semibold text-xs tracking-wide rounded-xl transition-colors shadow-sm"
            >
              Open Pipeline Canvas &rarr;
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
