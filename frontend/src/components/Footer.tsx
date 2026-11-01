import { useAccount } from '../hooks/useAccount';
import { SITE_LINK, SITE_PAGES } from './siteLinks';

const BAR = 'w-full shrink-0 bg-slate-950 border-t border-orange-500/20';
const ROW = [
  'w-full px-4 sm:px-8 md:px-12 py-5 flex flex-wrap items-center',
  'justify-between gap-x-6 gap-y-3',
].join(' ');

/**
 * The bar at the end of every page that has the top bar.
 */
export default function Footer() {
  const { state } = useAccount();
  return (
    <footer className={BAR}>
      <div className={ROW}>
        <div className="flex items-baseline gap-3">
          <span className="font-bold text-white tracking-tight">
            AtomField.
          </span>
          <span className="text-xs text-slate-400">
            © {new Date().getFullYear()} AtomField Labs
          </span>
        </div>
        <nav
          aria-label="Footer"
          className="flex flex-wrap items-center gap-x-4 sm:gap-x-6 gap-y-1"
        >
          <a
            href="#dashboard"
            className={SITE_LINK}
          >
            {state.status === 'signed-in' ? 'Sessions' : 'Sign in'}
          </a>
          {SITE_PAGES.map((page) => (
            <a
              key={page.href}
              href={page.href}
              className={SITE_LINK}
            >
              {page.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
