export default function HeroSection() {
  return (
    <section className="relative w-full h-screen flex flex-col items-center justify-center px-6 pointer-events-none">
      <div className="max-w-4xl mx-auto text-center pointer-events-auto">
        
        {/* Simple, Static Brand/Label */}
        <div className="inline-flex items-center mb-8 px-4 py-1.5 rounded-full bg-white/50 backdrop-blur-md border border-orange-500/20 shadow-sm">
          <span className="text-[11px] font-bold tracking-widest text-orange-700 uppercase">
            The New Standard in Simulation
          </span>
        </div>

        {/* Massive Brand Statement */}
        <h1 className="text-7xl md:text-9xl font-extrabold tracking-tight mb-4 text-slate-900 leading-[1.05] pb-2">
          AtomField.
        </h1>

        {/* Static, Confident Value Proposition */}
        <div className="mb-12 md:mb-16 flex items-center justify-center">
          <h2 className="text-2xl md:text-4xl font-extrabold text-slate-700 tracking-tight max-w-3xl mx-auto">
            The AI orchestrator for <span className="text-orange-600">materials discovery.</span>
          </h2>
        </div>

        {/* Center-justified Gist */}
        <p className="text-lg md:text-xl text-slate-600 mb-12 max-w-2xl mx-auto leading-relaxed text-center font-medium">
          Replace fragmented calculation tools with a unified, AI-driven physics pipeline. 
          AtomField accelerates hypothesis testing and theoretical discovery from single molecules to infinite crystal lattices.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <button className="px-8 py-3.5 rounded-lg bg-white/80 backdrop-blur text-slate-700 font-medium border border-slate-200 hover:border-slate-300 hover:text-orange-600 hover:bg-slate-50 transition-colors shadow-sm">
            Read the Documentation
          </button>
        </div>
      </div>
    </section>
  );
}
