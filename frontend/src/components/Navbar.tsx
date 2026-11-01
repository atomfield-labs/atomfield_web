import { useState, useEffect, useRef } from 'react';
import { useAccount } from '../hooks/useAccount';
import { SITE_LINK as LINK, SITE_PAGES } from './siteLinks';

const BAR = [
  'fixed top-0 left-0 w-full z-50 bg-slate-950 border-b',
  'border-orange-500/20 shadow-lg shadow-slate-900/10',
  'transition-transform duration-300 ease-in-out',
].join(' ');
const ROW = [
  'w-full px-4 sm:px-8 md:px-12 h-14 sm:h-16 flex items-center',
  'justify-between gap-4',
].join(' ');
const BRAND = [
  'font-bold text-lg sm:text-xl tracking-tight text-white',
  'group-hover:text-orange-500 transition-colors',
].join(' ');
// On a narrow window there's no room for these; the footer carries them.
const SITE_PAGE = `${LINK} hidden md:inline`;
// Whatever else doesn't fit scrolls within the bar.
const APP_LINKS = [
  'flex items-center gap-4 sm:gap-6 min-w-0 overflow-x-auto',
  'whitespace-nowrap [scrollbar-width:none]',
].join(' ');
// On the very narrowest phones the links need the room.
const ACCOUNT_NAME = 'max-w-24 lg:max-w-48 truncate max-[360px]:hidden';
const SHOWN = 'translate-y-0';
const HIDDEN = '-translate-y-full';
// Scrolled this far from the top, the bar may hide.
const TOP_ZONE_PX = 20;
// Ignore scroll jitter smaller than this.
const SCROLL_STEP_PX = 8;

/**
 * Slide the bar away while scrolling down; back when scrolling up or
 * near the top.
 */
function useShownOnScroll(): boolean {
  const [isVisible, setIsVisible] = useState(true);
  const lastScrollY = useRef(0);

  useEffect(() => {
    const handleScroll = (event: Event) => {
      const target = event.target;
      const currentScrollY =
        target instanceof HTMLElement
          ? target.scrollTop
          : window.scrollY || document.documentElement.scrollTop;
      if (currentScrollY <= TOP_ZONE_PX) {
        setIsVisible(true);
      } else if (currentScrollY > lastScrollY.current + SCROLL_STEP_PX) {
        setIsVisible(false);
      } else if (currentScrollY < lastScrollY.current - SCROLL_STEP_PX) {
        setIsVisible(true);
      }
      lastScrollY.current = currentScrollY;
    };

    const options = { capture: true, passive: true };
    window.addEventListener('scroll', handleScroll, options);
    return () =>
      window.removeEventListener('scroll', handleScroll, { capture: true });
  }, []);

  return isVisible;
}

/**
 * Who is signed in, with a way out; or the way in.
 */
function AccountLinks() {
  const { state, signOut } = useAccount();
  if (state.status === 'loading') return null;
  if (state.status === 'signed-out') {
    return (
      <a href="#dashboard" className={LINK}>
        Sign in
      </a>
    );
  }
  const { account } = state;
  return (
    <div className="flex items-center gap-4 sm:gap-6">
      <a href="#account" className={`${LINK} ${ACCOUNT_NAME}`}>
        {account.label || account.email}
      </a>
      <button
        type="button"
        onClick={() => void signOut()}
        className={`${LINK} cursor-pointer`}
      >
        Sign out
      </button>
    </div>
  );
}

export default function Navbar() {
  const isVisible = useShownOnScroll();
  const { state } = useAccount();
  const role = state.status === 'signed-in' ? state.account.role : null;

  return (
    <nav className={`${BAR} ${isVisible ? SHOWN : HIDDEN}`}>
      <div className={ROW}>
        <div className="flex items-center gap-4 sm:gap-8 md:gap-10 min-w-0">
          <a
            href="#"
            className="flex items-center shrink-0 cursor-pointer group"
          >
            <span className={BRAND}>AtomField.</span>
          </a>
          <div className={APP_LINKS}>
            <a href="#dashboard" className={LINK}>
              Sessions
            </a>
            {role === 'owner' && (
              <>
                <a href="#labs" className={LINK}>
                  Labs
                </a>
                <a href="#admin" className={LINK}>
                  Admin
                </a>
              </>
            )}
            {role === 'admin' && (
              <a href="#lab" className={LINK}>
                Lab
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 sm:gap-6 shrink-0">
          {SITE_PAGES.map((page) => (
            <a
              key={page.href}
              href={page.href}
              className={SITE_PAGE}
            >
              {page.label}
            </a>
          ))}
          <AccountLinks />
        </div>
      </div>
    </nav>
  );
}
