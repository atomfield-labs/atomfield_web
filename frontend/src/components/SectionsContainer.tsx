export default function SectionsContainer() {
  return (
    <>
      {/* Section 1: Nanoreactor (Active) */}
      <section className="w-full h-screen flex flex-col justify-center px-6 pointer-events-none">
        <div 
          onClick={() => window.location.hash = '#pipeline/nanoreactor'}
          className="w-full max-w-xl mr-0 md:mr-[5%] ml-auto bg-white/90 backdrop-blur-2xl p-10 rounded-3xl border border-white/60 shadow-xl shadow-slate-800/10 pointer-events-auto border-t-[4px] border-t-blue-500 cursor-pointer hover:scale-[1.02] transition-transform relative"
        >
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-4xl font-extrabold text-slate-900 tracking-tight">Nanoreactor & Catalysis</h2>
            <span className="px-3 py-1 bg-blue-100 text-blue-700 font-bold rounded-full text-xs animate-pulse">LIVE DEMO</span>
          </div>
          <p className="text-lg text-slate-700 font-medium leading-relaxed mb-6">
            Map transition states and calculate catalytic turnover frequencies in confined nanoscale environments using our prebuilt pipeline.
          </p>
          <div className="border-t border-slate-100 pt-6">
            <ul className="space-y-4">
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-blue-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Automated Transitions:</strong> Geometry Optimization &rarr; TS Search &rarr; Frequency Calculation executed entirely via graph orchestrator.</span>
              </li>
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-blue-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>No Setup Required:</strong> Click to launch the pre-configured workflow and instantly visualize intermediate results.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Section 2: Optoelectronics */}
      <section className="w-full h-screen flex flex-col justify-center px-6 pointer-events-none">
        <div className="w-full max-w-xl ml-0 md:ml-[5%] mr-auto bg-white/90 backdrop-blur-2xl p-10 rounded-3xl border border-white/60 shadow-xl shadow-slate-800/10 border-t-[4px] border-t-orange-500 relative">
          <span className="absolute top-4 right-6 px-3 py-1 bg-slate-200 text-slate-700 font-bold rounded-full text-xs">COMING SOON</span>
          <h2 className="text-4xl font-extrabold text-slate-900 mb-4 tracking-tight">Optoelectronic Properties</h2>
          <p className="text-lg text-slate-700 font-medium leading-relaxed mb-6">
            Visualize excited states instantly. Calculate UV-Vis absorption, emission probabilities, and 
            frontier orbital energy gaps directly from natural language prompts.
          </p>
          <div className="border-t border-slate-100 pt-6">
            <ul className="space-y-4">
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>No Command-Line Wrangling:</strong> Run high-accuracy TD-DFT calculations directly from the browser without touching an HPC cluster.</span>
              </li>
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Real-Time Insights:</strong> Monitor wave-function convergence and orbital electron densities as they calculate.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Section 3: Polymers */}
      <section className="w-full h-screen flex flex-col justify-center px-6 pointer-events-none">
        <div className="w-full max-w-xl mr-0 md:mr-[5%] ml-auto bg-white/90 backdrop-blur-2xl p-10 rounded-3xl border border-white/60 shadow-xl shadow-slate-800/10 border-t-[4px] border-t-orange-500 relative">
          <span className="absolute top-4 right-6 px-3 py-1 bg-slate-200 text-slate-700 font-bold rounded-full text-xs">COMING SOON</span>
          <h2 className="text-4xl font-extrabold text-slate-900 mb-4 tracking-tight">Polymer Chain Dynamics</h2>
          <p className="text-lg text-slate-700 font-medium leading-relaxed mb-6">
            Map entanglement and thermophysical properties. Simulate glass transitions, molecular weight distributions, 
            and complex rheology with uncompromised precision.
          </p>
          <div className="border-t border-slate-100 pt-6">
            <ul className="space-y-4">
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Democratized Simulation:</strong> Build complex, million-atom polymer topologies without writing a single line of input script.</span>
              </li>
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Publication-Ready Visualization:</strong> Hardware-accelerated graphics render physical stress-strain curves and scission events flawlessly.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Section 4: Solid State */}
      <section className="w-full h-screen flex flex-col justify-center px-6 pointer-events-none">
        <div className="w-full max-w-xl ml-0 md:ml-[5%] mr-auto bg-white/90 backdrop-blur-2xl p-10 rounded-3xl border border-white/60 shadow-xl shadow-slate-800/10 border-t-[4px] border-t-orange-500 relative">
          <span className="absolute top-4 right-6 px-3 py-1 bg-slate-200 text-slate-700 font-bold rounded-full text-xs">COMING SOON</span>
          <h2 className="text-4xl font-extrabold text-slate-900 mb-4 tracking-tight">Solid State & Lattices</h2>
          <p className="text-lg text-slate-700 font-medium leading-relaxed mb-6">
            From perovskites to battery electrolytes. Model infinite periodic systems, energy band structures, 
            state densities, and catalytic surface reactivity.
          </p>
          <div className="border-t border-slate-100 pt-6">
            <ul className="space-y-4">
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Physics & AI Integration:</strong> Interlace highly accurate Density Functional Theory (DFT) with lightning-fast machine-learned interatomic potentials.</span>
              </li>
              <li className="flex items-start text-slate-700">
                <svg className="w-6 h-6 text-orange-500 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                <span><strong>Fully Integrated Workflows:</strong> Stop managing separate file formats. Our cloud-native architecture natively handles structure generation, calculation, and analysis.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Section 5: The Orchestrator CTA */}
      <section className="w-full h-screen flex flex-col justify-center items-center px-6 text-center pointer-events-none">
        <div className="bg-white/90 backdrop-blur-2xl p-12 rounded-[2rem] border border-white/60 shadow-xl shadow-slate-800/10 max-w-3xl w-full flex flex-col items-center pointer-events-auto border-t-[8px] border-t-orange-500">
          <h2 className="text-5xl font-extrabold text-slate-900 mb-6 tracking-tight">Enter the Orchestrator.</h2>
          <p className="text-xl text-slate-600 mb-8 max-w-2xl leading-relaxed font-medium">
            The blank canvas where LLM-driven science happens. No cluttered toolbars. 
            Just pure intent, compiled into executing physics pipelines.
          </p>
          <div className="flex flex-wrap justify-center gap-3 mb-10">
            <span className="px-5 py-2 bg-slate-50 text-slate-700 rounded-full text-sm font-bold border border-slate-200">Natural Language Dispatch</span>
            <span className="px-5 py-2 bg-slate-50 text-slate-700 rounded-full text-sm font-bold border border-slate-200">Model Context Protocol (MCP)</span>
            <span className="px-5 py-2 bg-slate-50 text-slate-700 rounded-full text-sm font-bold border border-slate-200">Autonomous Agent Workflows</span>
          </div>
        </div>
      </section>
    </>
  )
}
