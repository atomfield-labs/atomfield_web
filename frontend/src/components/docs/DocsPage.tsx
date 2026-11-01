import { useEffect, useMemo, useRef, useState } from 'react';
import { useAccount } from '../../hooks/useAccount';
import { guidesFor, isGuide, loadGuide } from '../../content/guides';
import type { Guide } from '../../content/guides';
import { PAGE, PAGE_WIDTH } from '../dashboard/cardStyle';
import GuideText from './GuideText';

const LAYOUT = [
  'grid grid-cols-1 md:grid-cols-[14rem_minmax(0,1fr)] gap-6 lg:gap-10',
].join(' ');
const LIST = [
  'flex flex-wrap gap-x-4 md:block md:sticky md:top-24 md:self-start',
].join(' ');
const GROUP = 'contents md:block md:mb-5';
const GROUP_LABEL = [
  'hidden md:block mb-1 text-[11px] font-semibold tracking-wider',
  'uppercase text-slate-500',
].join(' ');
const LINK = 'block py-1 text-sm leading-snug transition-colors';
const LINK_OPEN = 'text-orange-600 font-medium';
const LINK_IDLE = 'text-slate-600 hover:text-orange-600';
const CARD = [
  'min-w-0 min-h-[60vh] bg-white rounded-xl border border-slate-200',
  'p-5 sm:p-8 lg:p-10',
].join(' ');
const NOTICE = 'text-sm text-slate-600';

/**
 * The guides this person may open, by group.
 */
function GuideList({ guides, openId }: { guides: Guide[]; openId?: string }) {
  const groups = [...new Set(guides.map((guide) => guide.group))];
  return (
    <nav
      aria-label="Guides"
      className={LIST}
    >
      {groups.map((group) => (
        <div
          key={group}
          className={GROUP}
        >
          <h2 className={GROUP_LABEL}>{group}</h2>
          {guides
            .filter((guide) => guide.group === group)
            .map((guide) => (
              <a
                key={guide.id}
                href={`#docs/${guide.id}`}
                aria-current={guide.id === openId ? 'page' : undefined}
                className={`${LINK} ${
                  guide.id === openId ? LINK_OPEN : LINK_IDLE
                }`}
              >
                {guide.title}
              </a>
            ))}
        </div>
      ))}
    </nav>
  );
}

/**
 * One guide, fetched when it opens.
 */
function GuideBody({ guide, guides }: { guide: Guide; guides: Guide[] }) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [hasFailed, setHasFailed] = useState(false);
  useEffect(() => {
    let active = true;
    loadGuide(guide.id)
      .then((text) => active && setMarkdown(text))
      .catch(() => active && setHasFailed(true));
    return () => {
      active = false;
    };
  }, [guide.id]);
  if (hasFailed) {
    return (
      <p
        role="alert"
        className={NOTICE}
      >
        Could not load this guide. Refresh to try again.
      </p>
    );
  }
  return markdown === null ? null : (
    <GuideText
      markdown={markdown}
      guides={guides}
    />
  );
}

/**
 * The documentation: a list of guides beside the open one. Open to
 * everyone; `guideId` comes from the address.
 */
export default function DocsPage({ guideId }: { guideId: string }) {
  const { state } = useAccount();
  const page = useRef<HTMLDivElement>(null);
  const role = state.status === 'signed-in' ? state.account.role : null;
  const guides = useMemo(() => guidesFor(role), [role]);
  const isLoading = state.status === 'loading';
  const isRefused =
    !isLoading &&
    isGuide(guideId) &&
    !guides.some((guide) => guide.id === guideId);
  const open = isRefused
    ? undefined
    : (guides.find((guide) => guide.id === guideId) ?? guides[0]);

  // Each guide starts at its top, whatever was being read before.
  useEffect(() => {
    page.current?.scrollIntoView({ block: 'start' });
  }, [guideId]);

  return (
    <div
      ref={page}
      className={`${PAGE} px-4 sm:px-8`}
    >
      <div className={`${PAGE_WIDTH} ${LAYOUT}`}>
        <GuideList
          guides={guides}
          openId={open?.id}
        />
        <article className={CARD}>
          {isRefused && (
            <p className={NOTICE}>This guide isn't open to you.</p>
          )}
          {open && !isLoading && (
            <GuideBody
              key={open.id}
              guide={open}
              guides={guides}
            />
          )}
        </article>
      </div>
    </div>
  );
}
