import { useState, useEffect } from 'react';
import { authService } from '../../api/services/authService';
import ApiKeyModal from '../auth/ApiKeyModal';
import type { SaveStatus } from '../../types/api';

interface EditorHeaderProps {
  activeSessionId: string;
  saveStatus: SaveStatus;
  quota?: number | null;
  isDeploying: boolean;
  onDeploy: () => void;
}

export default function EditorHeader({
  activeSessionId,
  saveStatus,
  quota: _quota,
  isDeploying,
  onDeploy,
}: EditorHeaderProps) {
  const isNanoreactor =
    activeSessionId === 'nanoreactor' || activeSessionId.startsWith('nanoreactor_');

  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  const checkAuthentication = async () => {
    const currentKey = authService.getStoredApiKey();
    if (!currentKey) {
      setIsAuthenticated(false);
      return;
    }

    try {
      const info = await authService.getMe();
      if (info && info.is_active) {
        setIsAuthenticated(true);
      } else {
        setIsAuthenticated(false);
      }
    } catch {
      setIsAuthenticated(false);
    }
  };

  useEffect(() => {
    checkAuthentication();
  }, []);

  const deployButtonLabel = isDeploying
    ? 'Deploying...'
    : isNanoreactor
    ? 'Run'
    : 'Deploy Pipeline';

  const handleDeployClick = () => {
    if (!isAuthenticated) {
      setIsApiKeyModalOpen(true);
      return;
    }
    onDeploy();
  };

  return (
    <>
      <div className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-6 shrink-0 z-10">
        <div className="flex items-center gap-3">
          <a
            href="#dashboard"
            title="Return to Sessions"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors group text-xs font-semibold"
          >
            <svg
              className="w-4 h-4 text-slate-400 group-hover:text-slate-700 transition-colors"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 19l-7-7m0 0l7-7m-7 7h18"
              />
            </svg>
            <span className="hidden sm:inline font-bold">Sessions</span>
          </a>
          <div className="h-6 w-px bg-slate-200" />
          <div className="flex flex-col">
            <span className="text-sm font-bold text-slate-800">
              {activeSessionId === 'nanoreactor'
                ? 'Nanoreactor Catalysis (Prebuilt)'
                : activeSessionId.startsWith('nanoreactor_')
                ? 'Nanoreactor Catalysis (Run)'
                : `Session: ${activeSessionId.substring(0, 14)}`}
            </span>
            {saveStatus === 'saving' && (
              <span className="text-[10px] text-orange-500 font-semibold animate-pulse">
                Saving...
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Server Connection Status (Connected = green dot, Disconnected = red dot) */}
          {isAuthenticated ? (
            <button
              onClick={() => setIsApiKeyModalOpen(true)}
              title="Server Connected (Authenticated with API Key) — Click for compute statistics"
              className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5 cursor-pointer hover:bg-emerald-100 transition-colors"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Connected
            </button>
          ) : (
            <button
              onClick={() => setIsApiKeyModalOpen(true)}
              title="Server Disconnected (API Key required) — Click to connect"
              className="px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200 flex items-center gap-1.5 cursor-pointer hover:bg-red-100 transition-colors"
            >
              <span className="w-2 h-2 rounded-full bg-red-500" />
              Disconnected
            </button>
          )}

          <button
            onClick={handleDeployClick}
            disabled={isDeploying}
            className="px-5 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-all shadow-md shadow-orange-600/20 active:scale-95 flex items-center gap-2"
          >
            {isDeploying && (
              <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {deployButtonLabel}
          </button>
        </div>
      </div>

      <ApiKeyModal
        isOpen={isApiKeyModalOpen}
        onClose={() => {
          setIsApiKeyModalOpen(false);
          checkAuthentication();
        }}
        onKeyChange={(_key) => {
          checkAuthentication();
        }}
      />
    </>
  );
}
