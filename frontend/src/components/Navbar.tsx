import { useState, useEffect, useRef } from 'react';
import { useAccount } from '../hooks/useAccount';

const BAR = [
  'fixed top-0 left-0 w-full z-50 bg-slate-950 border-b',
  'border-orange-500/20 shadow-lg shadow-slate-900/10',
  'transition-transform duration-300 ease-in-out',
].join(' ');
const LINK = [
  'text-xs sm:text-sm font-semibold tracking-wide text-slate-300',
  'hover:text-orange-400 transition-colors',
].join(' ');
const ROW = [
  'w-full px-4 sm:px-8 md:px-12 h-14 sm:h-16 flex items-center',
  'justify-between',
].join(' ');
const BRAND = [
  'font-bold text-lg sm:text-xl tracking-tight text-white',
  'group-hover:text-orange-500 transition-colors',
].join(' ');
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
      <a href="#account" className={`${LINK} max-w-48 truncate`}>
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
  const isOwner =
    state.status === 'signed-in' && state.account.role === 'owner';

  return (
    <nav className={`${BAR} ${isVisible ? SHOWN : HIDDEN}`}>
      <div className={ROW}>
        <div className="flex items-center gap-4 sm:gap-8 md:gap-10">
          <a href="#" className="flex items-center cursor-pointer group">
            <span className={BRAND}>AtomField.</span>
          </a>
          <div className="flex items-center gap-4 sm:gap-6">
            <a href="#dashboard" className={LINK}>
              Sessions
            </a>
            {isOwner && (
              <a href="#admin" className={LINK}>
                Admin
              </a>
            )}
          </div>
        </div>
        <AccountLinks />
      </div>
    </nav>
  );
}
