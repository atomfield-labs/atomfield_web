import { Fragment, Suspense } from 'react';
import type { ReactNode } from 'react';
import { Canvas } from '@react-three/fiber';
import PESTerrain from '../animations/PESTerrain';
import JablonskiDiagram from '../animations/JablonskiDiagram';
import IonLattice from '../animations/IonLattice';
import PolymerMelt from '../animations/PolymerMelt';
import {
  GROUP_LABEL,
  SECTION_HEAD,
  SECTION_SIDES,
  SECTION_TEXT,
  SECTION_TITLE,
  SECTION_WIDTH,
} from './landingStyle';

const NANOREACTOR_LINK = '#pipeline/new/nanoreactor';
// A new pipeline's start screen, which offers each template.
const NEW_PIPELINE_LINK = '#pipeline/new';

// The same gap across and down. A row with fewer cards sits in the middle.
const CARD_ROW = 'flex flex-wrap justify-center gap-8';
const MODULE_CARD = [
  'group relative flex flex-col overflow-hidden bg-white rounded-2xl',
  'border border-slate-200/90 shadow-xs hover:border-orange-500',
  'hover:shadow-card-lift hover:ring-2 hover:ring-orange-500/20',
  'hover:-translate-y-1.5 transition-all duration-300 ease-out',
  'w-full max-w-[420px] md:max-w-none md:w-[calc((100%-2rem)/2)]',
  'xl:w-[calc((100%-4rem)/3)]',
].join(' ');
const SCENE = [
  'w-full h-72 sm:h-80 bg-white relative overflow-hidden rounded-t-2xl',
  'border-b border-slate-100',
].join(' ');
const SCENE_LOADING = 'w-full h-full bg-slate-50 animate-pulse';
const STATE_LABEL = [
  'absolute px-2.5 py-1 rounded text-[10px] font-mono font-bold border',
  'shadow-xs pointer-events-none',
].join(' ');
// The same space on all four sides of a card's words.
const CARD_BODY = [
  'p-6 flex flex-col justify-between flex-1 items-center text-center',
  'bg-orange-100/90 border-t border-orange-200 rounded-b-2xl',
].join(' ');
const CARD_TITLE = [
  'text-xl font-bold text-slate-900 tracking-tight',
  'group-hover:text-orange-700 transition-colors',
].join(' ');
const CARD_TEXT = [
  'mt-2 min-h-[69px] text-sm text-slate-700 font-medium leading-relaxed',
].join(' ');
const CARD_TAGS = [
  'flex flex-wrap items-center justify-center gap-x-2 gap-y-1 mt-4',
  'min-h-[40px] text-xs font-mono font-semibold text-orange-700',
].join(' ');
const LAUNCH = [
  'w-full h-10 mt-6 px-4 bg-slate-900 group-hover:bg-orange-600',
  'text-white text-xs font-semibold tracking-wide rounded-xl transition-all',
  'duration-200 shadow-sm flex items-center justify-center gap-2',
  'cursor-pointer',
].join(' ');
const LAUNCH_ARROW = [
  'font-mono text-sm transform group-hover:translate-x-1',
  'transition-transform duration-200',
].join(' ');
const IN_DEVELOPMENT = [
  'w-full h-10 mt-6 px-4 bg-orange-200/60 border border-orange-300/80',
  'text-orange-900/70 text-xs font-semibold tracking-wide rounded-xl flex',
  'items-center justify-center gap-1.5',
].join(' ');

function open(link: string) {
  window.location.hash = link;
}

/**
 * A card's words: what it is, what it does, and what it uses.
 */
function CardBody({
  title,
  text,
  tags,
  children,
}: {
  title: string;
  text: string;
  tags: string[];
  children: ReactNode;
}) {
  return (
    <div className={CARD_BODY}>
      <div className="flex flex-col items-center w-full">
        <h3 className={CARD_TITLE}>{title}</h3>
        <p className={CARD_TEXT}>{text}</p>
        <div className={CARD_TAGS}>
          {tags.map((tag, index) => (
            <Fragment key={tag}>
              {index > 0 && <span className="text-orange-400">•</span>}
              <span>{tag}</span>
            </Fragment>
          ))}
        </div>
      </div>
      {children}
    </div>
  );
}

/**
 * The way into a workflow that can run today.
 */
function LaunchButton({ label, link }: { label: string; link: string }) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        open(link);
      }}
      className={LAUNCH}
    >
      <span>{label}</span>
      <span className={LAUNCH_ARROW}>&rarr;</span>
    </button>
  );
}

function InDevelopment() {
  return (
    <div className={IN_DEVELOPMENT}>
      <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
      <span>In Active Development</span>
    </div>
  );
}

export default function SectionsContainer() {
  return (
    <section
      id="modules-grid"
      className={`${SECTION_SIDES} py-8`}
    >
      <div className={SECTION_WIDTH}>
        <div className={SECTION_HEAD}>
          <h2 className={SECTION_TITLE}>
            Start from a workflow, make it yours
          </h2>
          <p className={SECTION_TEXT}>
            Ready-made pipelines you can open, change step by step and run on
            your own compute.
          </p>
        </div>

        <div className={CARD_ROW}>
          <div
            onClick={() => open(NANOREACTOR_LINK)}
            className={`${MODULE_CARD} cursor-pointer`}
          >
            <div className={SCENE}>
              <Suspense fallback={<div className={SCENE_LOADING} />}>
                <Canvas
                  camera={{ position: [0, 3.8, 11.6], fov: 45 }}
                  className="w-full h-full"
                >
                  <ambientLight intensity={1.2} />
                  <directionalLight
                    position={[10, 15, 10]}
                    intensity={1.8}
                    color="#ffffff"
                  />
                  <directionalLight
                    position={[-10, 10, -5]}
                    intensity={1.0}
                    color="#93c5fd"
                  />
                  <pointLight
                    position={[0, -2, 3]}
                    intensity={0.8}
                    color="#f97316"
                  />
                  <PESTerrain />
                </Canvas>
              </Suspense>
            </div>
            <CardBody
              title="Nanoreactor & Catalysis"
              text={
                'Explore reactions in accelerated reactive dynamics, map the ' +
                'network that appears, then refine products and transition ' +
                'states.'
              }
              tags={['xTB / GFN-FF', 'Reaction Networks', 'Transition States']}
            >
              <LaunchButton
                label="Launch Nanoreactor"
                link={NANOREACTOR_LINK}
              />
            </CardBody>
          </div>

          <div
            onClick={() => open(NEW_PIPELINE_LINK)}
            className={`${MODULE_CARD} cursor-pointer`}
          >
            <div className={SCENE}>
              <Suspense fallback={<div className={SCENE_LOADING} />}>
                <Canvas
                  camera={{ position: [0, 0, 13.0], fov: 45 }}
                  className="w-full h-full"
                >
                  <ambientLight intensity={1.2} />
                  <directionalLight
                    position={[10, 10, 10]}
                    intensity={1.8}
                    color="#ffffff"
                  />
                  <IonLattice />
                </Canvas>
              </Suspense>
            </div>
            <CardBody
              title="Solid State & Lattices"
              text={
                'Quantum ESPRESSO pipelines for crystals: ground state, ' +
                'bands, density of states and phonons, plus anomalous Hall ' +
                'conductivity.'
              }
              tags={['Quantum ESPRESSO', 'Phonons', 'Wannier90']}
            >
              <LaunchButton
                label="Launch Solid State"
                link={NEW_PIPELINE_LINK}
              />
            </CardBody>
          </div>
        </div>

        <h3 className={GROUP_LABEL}>In development</h3>

        <div className={CARD_ROW}>
          <div className={MODULE_CARD}>
            <div className={SCENE}>
              <Suspense fallback={<div className={SCENE_LOADING} />}>
                <Canvas
                  camera={{ position: [0, 0, 7.5], fov: 45 }}
                  className="w-full h-full"
                >
                  <ambientLight intensity={1.2} />
                  <directionalLight
                    position={[5, 10, 5]}
                    intensity={1.8}
                    color="#ffffff"
                  />
                  <pointLight
                    position={[0, 0, 4]}
                    intensity={0.6}
                    color="#ffffff"
                  />
                  <JablonskiDiagram />
                </Canvas>
              </Suspense>
              <div
                className={[
                  STATE_LABEL,
                  'left-4 bottom-4 bg-slate-100/90 text-slate-700',
                  'border-slate-200',
                ].join(' ')}
              >
                S₀ Ground
              </div>
              <div
                className={[
                  STATE_LABEL,
                  'left-4 top-4 bg-sky-50 text-sky-700 border-sky-200',
                ].join(' ')}
              >
                S₁ Singlet
              </div>
              <div
                className={[
                  STATE_LABEL,
                  'right-4 top-[42%] -translate-y-1/2 bg-pink-50',
                  'text-pink-700 border-pink-200',
                ].join(' ')}
              >
                T₁ Triplet
              </div>
            </div>
            <CardBody
              title="Optoelectronic Properties"
              text={
                'Electronic excited states, fluorescence and phosphorescence ' +
                'pathways, oscillator strengths and frontier orbital energies.'
              }
              tags={['TD-DFT', 'Singlet / Triplet', 'Oscillator Strength']}
            >
              <InDevelopment />
            </CardBody>
          </div>

          <div className={MODULE_CARD}>
            <div className={SCENE}>
              <Suspense fallback={<div className={SCENE_LOADING} />}>
                <Canvas
                  camera={{ position: [0, 0, 10], fov: 45 }}
                  className="w-full h-full"
                >
                  <ambientLight intensity={1.2} />
                  <directionalLight
                    position={[5, 10, 5]}
                    intensity={1.8}
                    color="#ffffff"
                  />
                  <pointLight
                    position={[0, 0, 3]}
                    intensity={0.8}
                    color="#ef4444"
                  />
                  <PolymerMelt />
                </Canvas>
              </Suspense>
            </div>
            <CardBody
              title="Polymer Chain Dynamics"
              text={
                'Macromolecular entanglement, stress-strain curves, glass ' +
                'transition temperatures (Tg) and mechanical bond scission.'
              }
              tags={[
                'Coarse-Grained MD',
                'Glass Transition (Tg)',
                'Bond Scission',
              ]}
            >
              <InDevelopment />
            </CardBody>
          </div>
        </div>
      </div>
    </section>
  );
}
