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
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 3.8, 11.6], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 15, 10]} intensity={1.8} color="#ffffff" />
                <directionalLight position={[-10, 10, -5]} intensity={1.0} color="#93c5fd" />
                <pointLight position={[0, -2, 3]} intensity={0.8} color="#f97316" />
                <PESTerrain />
              </Canvas>
            </Suspense>
          </div>

          {/* Darker Orange Shaded Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-orange-100/90 border-t border-orange-200 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-700 transition-colors">
                Nanoreactor & Catalysis
              </h3>
              <p className="text-xs text-slate-700 font-medium leading-relaxed mt-2">
                Discover reaction pathways and compute activation barriers (Ea) in accelerated reactive molecular environments with xTB and GFN-FF.
              </p>

              {/* Tags in Orange Color */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-3.5 text-xs font-mono font-semibold text-orange-700">
                <span>xTB / GFN-FF</span>
                <span className="text-orange-400">•</span>
                <span>PES Exploration</span>
                <span className="text-orange-400">•</span>
                <span>Barrier Estimation</span>
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
            <div className="absolute left-4 top-4 px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-sky-50 text-sky-700 border border-sky-200 shadow-xs pointer-events-none">
              S₁ Singlet
            </div>
            <div className="absolute right-4 top-[42%] -translate-y-1/2 px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-pink-50 text-pink-700 border border-pink-200 shadow-xs pointer-events-none">
              T₁ Triplet
            </div>
          </div>

          {/* Darker Orange Shaded Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-orange-100/90 border-t border-orange-200 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-700 transition-colors">
                Optoelectronic Properties
              </h3>
              <p className="text-xs text-slate-700 font-medium leading-relaxed mt-2">
                Calculate electronic excited states, fluorescence vs phosphorescence pathways, oscillator strengths, and frontier orbital energies.
              </p>

              {/* Tags in Orange Color */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-3.5 text-xs font-mono font-semibold text-orange-700">
                <span>TD-DFT</span>
                <span className="text-orange-400">•</span>
                <span>Singlet / Triplet</span>
                <span className="text-orange-400">•</span>
                <span>Oscillator Strength</span>
              </div>
            </div>

            {/* Simple Text Status */}
            <div className="mt-5 text-xs font-medium text-slate-500">
              In active development
            </div>
          </div>
        </div>

        {/* Card 3: Solid State (Third - Zoomed Out) */}
        <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden hover:-translate-y-1.5">
          {/* Dominant 3D Animation Header (Zoomed Out for Full Framing) */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 13.0], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 10, 10]} intensity={1.8} color="#ffffff" />
                <IonLattice />
              </Canvas>
            </Suspense>
          </div>

          {/* Darker Orange Shaded Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-orange-100/90 border-t border-orange-200 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-700 transition-colors">
                Solid State & Lattices
              </h3>
              <p className="text-xs text-slate-700 font-medium leading-relaxed mt-2">
                Model infinite crystal structures, phonon dispersions, and interstitial ion migration pathways in solid electrolytes and battery materials.
              </p>

              {/* Tags in Orange Color */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-3.5 text-xs font-mono font-semibold text-orange-700">
                <span>Periodic DFT</span>
                <span className="text-orange-400">•</span>
                <span>Phonon Dispersions</span>
                <span className="text-orange-400">•</span>
                <span>Ion Transport</span>
              </div>
            </div>

            {/* Simple Text Status */}
            <div className="mt-5 text-xs font-medium text-slate-500">
              In active development
            </div>
          </div>
        </div>

        {/* Card 4: Polymers (Fourth - Standalone in Row 2) */}
        <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-[0_20px_45px_-12px_rgba(249,115,22,0.18),0_4px_16px_rgba(0,0,0,0.04)] hover:border-orange-500 hover:ring-2 hover:ring-orange-500/20 transition-all duration-300 ease-out flex flex-col h-full overflow-hidden hover:-translate-y-1.5">
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-96 sm:h-[400px] bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 10], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={1.8} color="#ffffff" />
                <pointLight position={[0, 0, 3]} intensity={0.8} color="#ef4444" />
                <PolymerMelt />
              </Canvas>
            </Suspense>
          </div>

          {/* Darker Orange Shaded Text Section */}
          <div className="p-6 flex flex-col justify-between flex-1 bg-orange-100/90 border-t border-orange-200 rounded-b-2xl">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-orange-700 transition-colors">
                Polymer Chain Dynamics
              </h3>
              <p className="text-xs text-slate-700 font-medium leading-relaxed mt-2">
                Simulate macromolecular entanglement, stress-strain curves, glass transition temperatures (Tg), and mechanical bond scission events.
              </p>

              {/* Tags in Orange Color */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-3.5 text-xs font-mono font-semibold text-orange-700">
                <span>Coarse-Grained MD</span>
                <span className="text-orange-400">•</span>
                <span>Glass Transition (Tg)</span>
                <span className="text-orange-400">•</span>
                <span>Bond Scission</span>
              </div>
            </div>

            {/* Simple Text Status */}
            <div className="mt-5 text-xs font-medium text-slate-500">
              In active development
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
