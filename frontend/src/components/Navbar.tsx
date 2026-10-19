import { useState, useEffect } from 'react';
import { Key, Shield } from 'lucide-react';
import { authService } from '../api/services/authService';
import ApiKeyModal from './auth/ApiKeyModal';

export default function Navbar() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(authService.getStoredApiKey());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);

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

  return (
    <>
      <nav className="fixed top-0 left-0 w-full z-50 bg-slate-950 border-b border-orange-500/20 shadow-lg shadow-slate-900/10">
        <div className="w-full px-8 md:px-12 h-16 flex items-center justify-between">
          {/* Left Side: Brand Logo + Sessions Link */}
          <div className="flex items-center gap-10">
            {/* Brand / Logo */}
            <a href="#" className="flex items-center gap-3 cursor-pointer group">
              <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center shadow-inner group-hover:scale-110 transition-transform duration-300 border border-slate-700">
                <svg
                  className="w-5 h-5 text-orange-500"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
                  <ellipse cx="12" cy="12" rx="9" ry="3.5" transform="rotate(30 12 12)" />
                  <ellipse cx="12" cy="12" rx="9" ry="3.5" transform="rotate(90 12 12)" />
                  <ellipse cx="12" cy="12" rx="9" ry="3.5" transform="rotate(150 12 12)" />
                </svg>
              </div>
              <span className="font-bold text-xl tracking-tight text-white group-hover:text-orange-500 transition-colors">
                AtomField
              </span>
            </a>

            {/* Sessions & Admin Navigation Links */}
            <div className="flex items-center gap-4">
              <a
                href="#dashboard"
                className="text-sm font-semibold tracking-wide text-slate-300 hover:text-orange-400 transition-colors flex items-center gap-1.5"
              >
                <svg className="w-4 h-4 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
                Sessions
              </a>

              {isAdmin && (
                <a
                  href="#admin"
                  className="text-xs font-bold uppercase tracking-wider text-orange-400 hover:text-orange-300 bg-orange-950/60 hover:bg-orange-900/60 border border-orange-500/40 px-2.5 py-1 rounded-md transition-colors flex items-center gap-1.5"
                >
                  <Shield className="w-3.5 h-3.5 text-orange-400" />
                  Admin
                </a>
              )}
            </div>
          </div>

          {/* Right Side: Setup Key Button */}
          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsModalOpen(true)}
              className="px-3.5 py-1.5 text-xs font-semibold text-slate-200 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-sm"
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
