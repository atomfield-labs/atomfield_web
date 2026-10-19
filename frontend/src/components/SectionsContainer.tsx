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
          className="bg-white rounded-2xl border border-slate-200/90 shadow-sm hover:shadow-xl hover:border-blue-400 transition-all duration-300 flex flex-col overflow-hidden cursor-pointer group"
        >
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-88 sm:h-96 bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 2.8, 7.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 15, 10]} intensity={1.8} color="#ffffff" />
                <directionalLight position={[-10, 10, -5]} intensity={1.0} color="#93c5fd" />
                <pointLight position={[0, -2, 3]} intensity={0.8} color="#f97316" />
                <PESTerrain />
              </Canvas>
            </Suspense>
            <div className="absolute top-4 right-4 px-3 py-1 text-[11px] font-bold tracking-wider rounded-full bg-blue-50 text-blue-700 border border-blue-200/90 shadow-xs backdrop-blur-md">
              LIVE DEMO
            </div>
          </div>

          {/* Compact Text Section */}
          <div className="p-6 flex flex-col justify-between flex-grow">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight group-hover:text-blue-600 transition-colors">
                Nanoreactor & Catalysis
              </h3>
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wider mt-1">
                Reaction Networks & Transition State Search
              </p>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2.5">
                Discover reaction pathways and compute activation barriers ($E_a$) in accelerated reactive molecular environments with xTB and GFN-FF.
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.location.hash = '#pipeline/nanoreactor';
              }}
              className="w-full mt-5 py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold tracking-wide rounded-xl transition-colors shadow-sm flex items-center justify-center gap-2"
            >
              Launch Nanoreactor &rarr;
            </button>
          </div>
        </div>

        {/* Card 2: Optoelectronics (Second) */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-88 sm:h-96 bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 7.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={1.8} color="#ffffff" />
                <JablonskiDiagram />
              </Canvas>
            </Suspense>
            {/* Crisp State Overlays */}
            <div className="absolute left-4 bottom-4 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 text-slate-700 border border-slate-200 shadow-xs pointer-events-none">
              S₀ Ground
            </div>
            <div className="absolute left-4 top-4 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-50 text-sky-700 border border-sky-200 shadow-xs pointer-events-none">
              S₁ Singlet
            </div>
            <div className="absolute right-4 bottom-14 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-pink-50 text-pink-700 border border-pink-200 shadow-xs pointer-events-none">
              T₁ Triplet
            </div>
            <div className="absolute top-4 right-4 px-3 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              COMING SOON
            </div>
          </div>

          {/* Compact Text Section */}
          <div className="p-6 flex flex-col justify-between flex-grow">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Optoelectronic Properties
              </h3>
              <p className="text-xs font-semibold text-orange-600 uppercase tracking-wider mt-1">
                TD-DFT Excited States & UV-Vis Spectra
              </p>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2.5">
                Calculate electronic excited states, fluorescence vs phosphorescence pathways, oscillator strengths, and frontier orbital energies directly in-browser.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: TD-DFT</span>
            </div>
          </div>
        </div>

        {/* Card 3: Solid State (Third) */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-88 sm:h-96 bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 8.5], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[10, 10, 10]} intensity={1.8} color="#ffffff" />
                <IonLattice />
              </Canvas>
            </Suspense>
            <div className="absolute top-4 right-4 px-3 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              COMING SOON
            </div>
          </div>

          {/* Compact Text Section */}
          <div className="p-6 flex flex-col justify-between flex-grow">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Solid State & Lattices
              </h3>
              <p className="text-xs font-semibold text-purple-600 uppercase tracking-wider mt-1">
                Periodic DFT & Ion Transport Dynamics
              </p>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2.5">
                Model infinite crystal structures, phonon dispersions, and interstitial ion migration pathways in solid electrolytes and battery cathode materials.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: Plane-Wave DFT</span>
            </div>
          </div>
        </div>

        {/* Card 4: Polymers (Fourth - Standalone in Row 2) */}
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm hover:shadow-xl hover:border-slate-300 transition-all duration-300 flex flex-col overflow-hidden">
          {/* Dominant 3D Animation Header with White Background */}
          <div className="w-full h-88 sm:h-96 bg-white relative overflow-hidden rounded-t-2xl border-b border-slate-100">
            <Suspense fallback={<div className="w-full h-full bg-slate-50 animate-pulse" />}>
              <Canvas camera={{ position: [0, 0, 10], fov: 45 }} className="w-full h-full">
                <ambientLight intensity={1.2} />
                <directionalLight position={[5, 10, 5]} intensity={1.8} color="#ffffff" />
                <pointLight position={[0, 0, 3]} intensity={0.8} color="#ef4444" />
                <PolymerMelt />
              </Canvas>
            </Suspense>
            <div className="absolute top-4 right-4 px-3 py-1 text-[11px] font-bold tracking-wider rounded-full bg-slate-100 text-slate-600 border border-slate-200 shadow-xs backdrop-blur-md">
              COMING SOON
            </div>
          </div>

          {/* Compact Text Section */}
          <div className="p-6 flex flex-col justify-between flex-grow">
            <div>
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                Polymer Chain Dynamics
              </h3>
              <p className="text-xs font-semibold text-rose-600 uppercase tracking-wider mt-1">
                Chain Entanglement & Rheology
              </p>
              <p className="text-xs text-slate-600 font-medium leading-relaxed mt-2.5">
                Simulate macromolecular entanglement, stress-strain curves, glass transition temperatures ($T_g$), and mechanical bond scission events.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Status: Roadmap</span>
              <span>Engine: MD / GROMACS</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
