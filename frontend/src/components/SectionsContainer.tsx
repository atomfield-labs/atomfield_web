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
        <div className="inline-flex items-center gap-2 mb-2.5">
          <span className="h-px w-6 bg-orange-500" />
          <span className="text-[11px] font-mono font-bold tracking-widest text-orange-600 uppercase">
            Simulation Engines
          </span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900">
          Calculation Modules
        </h2>
        <p className="text-base text-slate-600 mt-2 font-medium">
          Preconfigured high-throughput quantum chemistry and molecular dynamics workflows.
        </p>
      </div>

      {/* 3-Cards Per Row Responsive Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8 w-full">
        {/* Card 1: Nanoreactor (First) */}
        <div 
          onClick={() => window.location.hash = '#pipeline/nanoreactor'}
          className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden cursor-pointer hover:-translate-y-1.5"
        >
          {/* Dominant 3D Animation Header (Zoomed Out for Full Framing) */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            {/* Viewport Meta Label */}
            <div className="absolute top-4 left-4 z-10 px-2.5 py-1 rounded bg-slate-900/5 border border-slate-200/70 text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase pointer-events-none backdrop-blur-xs">
              01 // CATALYSIS
            </div>

            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 3.8, 11.6], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 15, 10]} intensity={1.8} color="#ffffff" />
                <directionalLight position={[-10, 10, -5]} intensity={1.0} color="#93c5fd" />
                <pointLight position={[0, -2, 3]} intensity={0.8} color="#f97316" />
                <PESTerrain />
              </Canvas>
            </Suspense>

            {/* Pulsing Active Badge */}
            <div className="absolute top-4 right-4 z-10 inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-mono font-bold tracking-wider rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/90 shadow-xs backdrop-blur-md">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              ACTIVE WORKFLOW
            </div>
          </div>

          {/* Light Orange Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-gradient-to-b from-orange-50/50 via-orange-50/75 to-orange-100/50 border-t border-orange-200/60 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-600 transition-colors">
                Nanoreactor & Catalysis
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2">
                Discover reaction pathways and compute activation barriers (Ea) in accelerated reactive molecular environments with xTB and GFN-FF.
              </p>

              {/* Technical Method Chips */}
              <div className="flex flex-wrap gap-1.5 mt-3.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  xTB / GFN-FF
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  PES Exploration
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Barrier Estimation
                </span>
              </div>
            </div>

            {/* Action Button */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.location.hash = '#pipeline/nanoreactor';
              }}
              className="w-full mt-5 py-2.5 px-4 bg-slate-900 group-hover:bg-orange-600 text-white text-xs font-semibold tracking-wide rounded-xl transition-all duration-200 shadow-sm flex items-center justify-between cursor-pointer"
            >
              <span>Launch Nanoreactor</span>
              <span className="font-mono text-sm transform group-hover:translate-x-1 transition-transform duration-200">&rarr;</span>
            </button>
          </div>
        </div>

        {/* Card 2: Optoelectronics (Second) */}
        <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden hover:-translate-y-1.5">
          {/* Dominant 3D Animation Header */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            {/* Viewport Meta Label */}
            <div className="absolute top-4 left-4 z-10 px-2.5 py-1 rounded bg-slate-900/5 border border-slate-200/70 text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase pointer-events-none backdrop-blur-xs">
              02 // SPECTROSCOPY
            </div>

            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 7.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={1.8} color="#ffffff" />
                <pointLight position={[0, 0, 4]} intensity={0.6} color="#ffffff" />
                <JablonskiDiagram />
              </Canvas>
            </Suspense>

            {/* Crisp State Overlays - Triplet placed at Middle Bands with clear margin */}
            <div className="absolute left-4 bottom-4 px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-slate-100/90 text-slate-700 border border-slate-200 shadow-xs pointer-events-none">
              S₀ Ground
            </div>
            <div className="absolute left-4 top-12 px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-sky-50 text-sky-700 border border-sky-200 shadow-xs pointer-events-none">
              S₁ Singlet
            </div>
            <div className="absolute right-4 top-[42%] -translate-y-1/2 px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-pink-50 text-pink-700 border border-pink-200 shadow-xs pointer-events-none">
              T₁ Triplet
            </div>
            <div className="absolute top-4 right-4 z-10 inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-mono font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
              COMING SOON
            </div>
          </div>

          {/* Light Orange Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-gradient-to-b from-orange-50/50 via-orange-50/75 to-orange-100/50 border-t border-orange-200/60 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-600 transition-colors">
                Optoelectronic Properties
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2">
                Calculate electronic excited states, fluorescence vs phosphorescence pathways, oscillator strengths, and frontier orbital energies.
              </p>

              {/* Technical Method Chips */}
              <div className="flex flex-wrap gap-1.5 mt-3.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  TD-DFT
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Singlet / Triplet
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Oscillator Strength
                </span>
              </div>
            </div>

            {/* Status Footer */}
            <div className="mt-5 w-full py-2.5 px-4 bg-white/70 border border-orange-200/80 text-slate-500 text-xs font-mono rounded-xl flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />
                In Active Development
              </span>
              <span className="text-[10.5px] text-slate-400 font-semibold">v0.4 Pipeline</span>
            </div>
          </div>
        </div>

        {/* Card 3: Solid State (Third - Zoomed Out) */}
        <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden hover:-translate-y-1.5">
          {/* Dominant 3D Animation Header (Zoomed Out for Full Framing) */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            {/* Viewport Meta Label */}
            <div className="absolute top-4 left-4 z-10 px-2.5 py-1 rounded bg-slate-900/5 border border-slate-200/70 text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase pointer-events-none backdrop-blur-xs">
              03 // MATERIALS
            </div>

            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 13.0], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 10, 10]} intensity={1.8} color="#ffffff" />
                <IonLattice />
              </Canvas>
            </Suspense>

            <div className="absolute top-4 right-4 z-10 inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-mono font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
              COMING SOON
            </div>
          </div>

          {/* Light Orange Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-gradient-to-b from-orange-50/50 via-orange-50/75 to-orange-100/50 border-t border-orange-200/60 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-600 transition-colors">
                Solid State & Lattices
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2">
                Model infinite crystal structures, phonon dispersions, and interstitial ion migration pathways in solid electrolytes and battery materials.
              </p>

              {/* Technical Method Chips */}
              <div className="flex flex-wrap gap-1.5 mt-3.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Periodic DFT
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Phonon Dispersions
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Ion Transport
                </span>
              </div>
            </div>

            {/* Status Footer */}
            <div className="mt-5 w-full py-2.5 px-4 bg-white/70 border border-orange-200/80 text-slate-500 text-xs font-mono rounded-xl flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />
                In Active Development
              </span>
              <span className="text-[10.5px] text-slate-400 font-semibold">v0.4 Pipeline</span>
            </div>
          </div>
        </div>

        {/* Card 4: Polymers (Fourth - Standalone in Row 2) */}
        <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden hover:-translate-y-1.5">
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            {/* Viewport Meta Label */}
            <div className="absolute top-4 left-4 z-10 px-2.5 py-1 rounded bg-slate-900/5 border border-slate-200/70 text-[10px] font-mono font-bold tracking-wider text-slate-600 uppercase pointer-events-none backdrop-blur-xs">
              04 // MACROMOLECULES
            </div>

            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 10], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={1.8} color="#ffffff" />
                <pointLight position={[0, 0, 3]} intensity={0.8} color="#ef4444" />
                <PolymerMelt />
              </Canvas>
            </Suspense>

            <div className="absolute top-4 right-4 z-10 inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-mono font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
              COMING SOON
            </div>
          </div>

          {/* Light Orange Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-gradient-to-b from-orange-50/50 via-orange-50/75 to-orange-100/50 border-t border-orange-200/60 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-600 transition-colors">
                Polymer Chain Dynamics
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2">
                Simulate macromolecular entanglement, stress-strain curves, glass transition temperatures (Tg), and mechanical bond scission events.
              </p>

              {/* Technical Method Chips */}
              <div className="flex flex-wrap gap-1.5 mt-3.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Coarse-Grained MD
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Glass Transition (Tg)
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-white/90 text-orange-900 border border-orange-200/80 shadow-2xs">
                  Bond Scission
                </span>
              </div>
            </div>

            {/* Status Footer */}
            <div className="mt-5 w-full py-2.5 px-4 bg-white/70 border border-orange-200/80 text-slate-500 text-xs font-mono rounded-xl flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />
                In Active Development
              </span>
              <span className="text-[10.5px] text-slate-400 font-semibold">v0.4 Pipeline</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}