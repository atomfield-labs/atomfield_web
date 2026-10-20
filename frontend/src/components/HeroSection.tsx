import PipelineFlowHero from './animations/PipelineFlowHero';

export default function HeroSection() {
  return (
    <section className="relative w-full min-h-[80vh] flex flex-col justify-center px-6 sm:px-10 md:px-12 lg:px-16 pt-24 sm:pt-28 pb-12">
      <div className="max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-center">
        
        {/* Left Column: Prominent, Bigger Text (The Main Thing) */}
        <div className="lg:col-span-6 flex flex-col items-start text-left">
          {/* Brand Label */}
          <div className="inline-flex items-center mb-5 px-4 py-1.5 rounded-full bg-white/80 backdrop-blur-md border border-orange-500/20 shadow-xs">
            <span className="text-xs font-bold tracking-widest text-orange-700 uppercase">
              The Modern Standard in Simulation
            </span>
          </div>

          {/* Clean Brand Statement - Prominent, No Logo on Left */}
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-slate-900 leading-[1.08] mb-4">
            AtomField.
          </h1>

          {/* Value Proposition */}
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-800 tracking-tight leading-snug mb-5 max-w-xl">
            Create your own computational pipeline for <span className="text-orange-600">materials discovery.</span>
          </h2>

          {/* Paragraph */}
          <p className="text-base sm:text-lg text-slate-600 mb-9 leading-relaxed font-normal max-w-xl">
            Replace fragmented scripts and manual workflows with an automated, high-throughput simulation pipeline. 
            AtomField orchestrates quantum chemistry, reaction network discovery, and molecular dynamics from single molecules to infinite crystal lattices.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-start gap-4 w-full sm:w-auto">
            <button 
              onClick={() => window.location.hash = '#pipeline/nanoreactor'}
              className="px-7 py-3.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-base font-semibold transition-colors shadow-sm cursor-pointer flex items-center justify-center gap-2"
            >
              <span>Launch Nanoreactor Demo</span>
              <span>&rarr;</span>
            </button>
            <button 
              onClick={() => {
                const el = document.getElementById('modules-grid');
                el?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="px-7 py-3.5 rounded-xl bg-white/90 backdrop-blur text-slate-700 text-base font-medium border border-slate-200 hover:border-slate-300 hover:text-orange-600 hover:bg-slate-50 transition-colors shadow-sm cursor-pointer flex items-center justify-center gap-1.5"
            >
              <span>Explore Modules</span>
              <span>&darr;</span>
            </button>
          </div>
        </div>

        {/* Right Column: Symbolic Pure Nodes Animation (Pasted directly on landing page) */}
        <div className="lg:col-span-6 w-full flex items-center justify-center">
          <PipelineFlowHero />
        </div>

      </div>
    </section>
  );
}
