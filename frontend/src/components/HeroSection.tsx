import PipelineFlowHero from './animations/PipelineFlowHero';
import { SECTION_SIDES, SECTION_WIDTH } from './landingStyle';

const SECTION = [
  `relative min-h-[80vh] flex flex-col justify-center ${SECTION_SIDES}`,
  'pt-24 sm:pt-28 pb-8',
].join(' ');
const LAYOUT = [
  `${SECTION_WIDTH} w-full grid grid-cols-1 lg:grid-cols-12`,
  'gap-10 lg:gap-14 items-center',
].join(' ');
const PILL = [
  'inline-flex items-center mb-5 px-4 py-1.5 rounded-full bg-white/80',
  'backdrop-blur-md border border-orange-500/20 shadow-xs',
].join(' ');
const PILL_TEXT = 'text-xs font-bold tracking-widest text-orange-700 uppercase';
const BRAND = [
  'text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight',
  'text-slate-900 leading-[1.08] mb-4',
].join(' ');
const SUBTEXT = [
  'grid text-2xl sm:text-3xl font-extrabold text-slate-800 tracking-tight',
  'leading-snug mb-5 max-w-xl',
].join(' ');
// One cell for both, so the points below stay put when the motto gives
// way to the sentence (the timing is in index.css).
const MOTTO = 'hero-motto col-start-1 row-start-1';
const FIELD = 'hero-field col-start-1 row-start-1';
// The motto again, for good, once the sentence has taken its place.
const KEPT_MOTTO = [
  'hero-kept-motto mt-6 text-lg sm:text-xl font-extrabold tracking-tight',
  'text-slate-800',
].join(' ');
const FIGURE = 'lg:col-span-6 w-full flex flex-col items-center justify-center';
const POINTS_LIST = 'flex flex-col gap-3 mb-9 max-w-xl';
const POINT = 'flex gap-3 text-base leading-relaxed text-pretty text-slate-600';
const POINT_MARK = 'mt-2.5 w-1.5 h-1.5 shrink-0 rounded-full bg-orange-500';
const POINT_LEAD = 'font-semibold text-slate-900';
const ACTIONS = [
  'flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center',
  'justify-start gap-3 w-full sm:w-auto',
].join(' ');
// Less padding from lg to xl, where both buttons must fit in half the page.
const PRIMARY = [
  'px-7 lg:px-4 xl:px-7 py-3.5 rounded-xl bg-slate-900 hover:bg-slate-800',
  'text-white text-base font-semibold border border-transparent',
  'transition-colors shadow-sm cursor-pointer whitespace-nowrap',
  'flex items-center justify-center gap-2',
].join(' ');
const SECONDARY = [
  'px-7 lg:px-4 xl:px-7 py-3.5 rounded-xl bg-white/90 backdrop-blur',
  'text-slate-700 text-base font-medium border border-slate-200',
  'hover:border-slate-300 hover:text-orange-600 hover:bg-slate-50',
  'transition-colors shadow-sm cursor-pointer whitespace-nowrap',
  'flex items-center justify-center gap-1.5',
].join(' ');
const POINTS = [
  {
    lead: 'Modular workflow nodes, like Lego.',
    rest: 'Snap them together. No scripting.',
  },
  {
    lead: 'Physics first, AI assists.',
    rest:
      'Simulation packages are complex enough, so every step stays visible.',
  },
  {
    lead: 'Design your own deterministic workflows.',
    rest: 'No costly AI hallucinations.',
  },
  {
    lead: 'Your intellect. Your compute. Your data privacy.',
    rest: 'Jobs run on your cluster, under your control.',
  },
  {
    lead: 'Learn by doing the science.',
    rest: 'Set the parameters. Understand the results.',
  },
];

export default function HeroSection() {
  const exploreWorkflows = () => {
    const workflows = document.getElementById('modules-grid');
    workflows?.scrollIntoView({ behavior: 'smooth' });
  };
  return (
    <section className={SECTION}>
      <div className={LAYOUT}>
        <div className="lg:col-span-6 flex flex-col items-start text-left">
          <div className={PILL}>
            <span className={PILL_TEXT}>Modern standard in simulation</span>
          </div>

          <h1 className={BRAND}>AtomField.</h1>

          <h2 className={SUBTEXT}>
            <span className={MOTTO}>
              <span>Design.</span> <span>Simulate.</span>{' '}
              <span className="text-orange-600">Discover.</span>
            </span>
            <span className={FIELD}>
              DAG workflows for computational chemistry and{' '}
              <span className="text-orange-600">materials science.</span>
            </span>
          </h2>

          <ul className={POINTS_LIST}>
            {POINTS.map((point) => (
              <li
                key={point.lead}
                className={POINT}
              >
                <span
                  aria-hidden="true"
                  className={POINT_MARK}
                />
                <span>
                  <span className={POINT_LEAD}>{point.lead}</span> {point.rest}
                </span>
              </li>
            ))}
          </ul>

          <div className={ACTIONS}>
            <button
              type="button"
              onClick={() => (window.location.hash = '#pipeline/new')}
              className={PRIMARY}
            >
              <span>Build Your Pipeline</span>
              <span>&rarr;</span>
            </button>
            <button
              type="button"
              onClick={exploreWorkflows}
              className={SECONDARY}
            >
              <span>Explore Workflows</span>
              <span>&darr;</span>
            </button>
          </div>
        </div>

        <div className={FIGURE}>
          <PipelineFlowHero />
          <p className={KEPT_MOTTO}>
            Design. Simulate.{' '}
            <span className="text-orange-600">Discover.</span>
          </p>
        </div>
      </div>
    </section>
  );
}
