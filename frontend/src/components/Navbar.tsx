import { useState, useEffect, useRef } from 'react';
import { Key } from 'lucide-react';
import { authService } from '../api/services/authService';
import ApiKeyModal from './auth/ApiKeyModal';

export default function Navbar() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(authService.getStoredApiKey());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [isVisible, setIsVisible] = useState(true);
  const lastScrollY = useRef(0);

  const checkAuth = async () => {
    const currentKey = authService.getStoredApiKey();
    setApiKey(currentKey);
    if (!currentKey) {
      setIsAuthenticated(false);
      setIsAdmin(false);
      return;
    }

    try {
      const info = await authService.getMe();
      setIsAuthenticated(Boolean(info && info.is_active));
      setIsAdmin(Boolean(info && info.is_admin));
    } catch {
      setIsAuthenticated(false);
      setIsAdmin(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, [apiKey]);

  // Handle scroll to slide up on scroll down, and slide down when scrolling up or at top
  useEffect(() => {
    const handleScroll = (e: Event) => {
      const target = e.target;
      let currentScrollY = 0;
      if (target instanceof HTMLElement) {
        currentScrollY = target.scrollTop;
      } else if (target === document || target === window) {
        currentScrollY = window.scrollY || document.documentElement.scrollTop;
      }

      // If at or near the top, always show
      if (currentScrollY <= 20) {
        setIsVisible(true);
      } else if (currentScrollY > lastScrollY.current + 8) {
        // Scrolling down -> slide up and disappear
        setIsVisible(false);
      } else if (currentScrollY < lastScrollY.current - 8) {
        // Scrolling up -> slide down into view
        setIsVisible(true);
      }

      lastScrollY.current = currentScrollY;
    };

    window.addEventListener('scroll', handleScroll, { capture: true, passive: true });
    return () => window.removeEventListener('scroll', handleScroll, { capture: true });
  }, []);

  return (
    <>
      <nav
        className={`fixed top-0 left-0 w-full z-50 bg-slate-950 border-b border-orange-500/20 shadow-lg shadow-slate-900/10 transition-transform duration-300 ease-in-out ${
          isVisible ? 'translate-y-0' : '-translate-y-full'
        }`}
      >
        <div className="w-full px-4 sm:px-8 md:px-12 h-14 sm:h-16 flex items-center justify-between">
          {/* Left Side: Brand Text + Navigation Links */}
          <div className="flex items-center gap-4 sm:gap-8 md:gap-10">
            {/* Brand (Icon removed, clean text) */}
            <a href="#" className="flex items-center cursor-pointer group">
              <span className="font-bold text-lg sm:text-xl tracking-tight text-white group-hover:text-orange-500 transition-colors">
                AtomField.
              </span>
            </a>

            {/* Sessions & Admin Navigation Links */}
            <div className="flex items-center gap-4 sm:gap-6">
              <a
                href="#dashboard"
                className="text-xs sm:text-sm font-semibold tracking-wide text-slate-300 hover:text-orange-400 transition-colors"
              >
                Sessions
              </a>

              {isAdmin && (
                <a
                  href="#admin"
                  className="text-xs sm:text-sm font-semibold tracking-wide text-slate-300 hover:text-orange-400 transition-colors"
                >
                  Admin
                </a>
              )}
            </div>
          </div>

          {/* Right Side: Setup Key Button */}
          <div className="flex items-center gap-2 sm:gap-4">
            <button
              onClick={() => setIsModalOpen(true)}
              className="px-2.5 sm:px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              <Key className="w-3.5 h-3.5 text-orange-500" />
              <span>{isAuthenticated ? 'API Key' : 'Setup Key'}</span>
            </button>
          </div>
        </div>
      </nav>

      <ApiKeyModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          checkAuth();
        }}
        onKeyChange={() => {
          checkAuth();
        }}
      />
    </>
  );
}
