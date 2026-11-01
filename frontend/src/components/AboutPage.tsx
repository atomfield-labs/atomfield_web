import { ABOUT } from '../content/about';
import { CARD, CARD_GRID, PAGE, PAGE_WIDTH } from './dashboard/cardStyle';

const HEADLINE = [
  'text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900',
].join(' ');
const PROMISE_TITLE = [
  'mb-2 text-lg font-bold text-slate-800 group-hover:text-orange-600',
  'transition-colors',
].join(' ');
const LABEL = [
  'text-[11px] font-semibold tracking-wider uppercase text-slate-500',
].join(' ');

/**
 * What AtomField is, what it promises, and who built it. The words are in
 * content/about.ts.
 */
export default function AboutPage() {
  const { builtBy } = ABOUT;
  return (
    <div className={`${PAGE} px-4 sm:px-8`}>
      <div className={PAGE_WIDTH}>
        <header className="max-w-3xl mx-auto mb-12 text-center">
          <h1 className={HEADLINE}>{ABOUT.headline}</h1>
          <p className="mt-5 text-lg leading-relaxed text-slate-600">
            {ABOUT.intro}
          </p>
          <p className="mt-3 text-base leading-relaxed text-slate-600">
            {ABOUT.audience}
          </p>
        </header>
        <div className={CARD_GRID}>
          {ABOUT.promises.map((promise) => (
            <section
              key={promise.title}
              className="group text-center"
            >
              <div className={CARD}>
                <h2 className={PROMISE_TITLE}>{promise.title}</h2>
                <p className="text-sm leading-relaxed text-slate-600">
                  {promise.text}
                </p>
              </div>
            </section>
          ))}
        </div>
        <section className="max-w-2xl mx-auto mt-14 mb-6 text-center">
          <h2 className={LABEL}>Built by</h2>
          <p className="mt-2 text-xl font-bold text-slate-900">
            {builtBy.name}
          </p>
          <p className="mt-1 text-sm text-slate-600">{builtBy.role}</p>
          {builtBy.bio && (
            <p className="mt-4 text-base leading-relaxed text-slate-600">
              {builtBy.bio}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
