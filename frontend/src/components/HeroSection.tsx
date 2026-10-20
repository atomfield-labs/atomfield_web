export default function HeroSection() {
  return (
    <section className="relative w-full min-h-[72vh] flex flex-col items-center justify-center px-6 pt-24 pb-12">
      <div className="max-w-4xl mx-auto text-center">
        
        {/* Brand Label */}
        <div className="inline-flex items-center mb-8 px-4 py-1.5 rounded-full bg-white/70 backdrop-blur-md border border-orange-500/20 shadow-sm">
          <span className="text-[11px] font-bold tracking-widest text-orange-700 uppercase">
            The Modern Standard in Simulation
          </span>
        </div>

        {/* Brand Statement */}
        <h1 className="text-7xl md:text-9xl font-extrabold tracking-tight mb-4 text-slate-900 leading-[1.05] pb-2">
          AtomField.
        </h1>

        {/* Value Proposition */}
        <div className="mb-8 md:mb-10 flex items-center justify-center">
          <h2 className="text-2xl md:text-4xl font-extrabold text-slate-700 tracking-tight max-w-3xl mx-auto">
            The computational orchestrator for <span className="text-orange-600">materials discovery.</span>
          </h2>
        </div>

        {/* Paragraph */}
        <p className="text-lg md:text-xl text-slate-600 mb-10 max-w-2xl mx-auto leading-relaxed text-center font-medium">
          Replace fragmented scripts and manual workflows with an automated, high-throughput simulation pipeline. 
          AtomField orchestrates quantum chemistry, reaction network discovery, and molecular dynamics from single molecules to infinite crystal lattices.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <button 
            onClick={() => window.location.hash = '#pipeline/nanoreactor'}
            className="px-8 py-3.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-semibold transition-colors shadow-sm cursor-pointer"
          >
            Launch Nanoreactor Demo &rarr;
          </button>
          <button 
            onClick={() => {
              const el = document.getElementById('modules-grid');
              el?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="px-8 py-3.5 rounded-xl bg-white/90 backdrop-blur text-slate-700 font-medium border border-slate-200 hover:border-slate-300 hover:text-orange-600 hover:bg-slate-50 transition-colors shadow-sm cursor-pointer"
          >
            Explore Modules &darr;
          </button>
        </div>
      </div>
    </section>
  );
}
