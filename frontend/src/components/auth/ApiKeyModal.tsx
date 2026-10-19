import { useState, useEffect } from 'react';
import {
  Copy,
  Check,
  RefreshCw,
  X,
} from 'lucide-react';
import { authService } from '../../api/services/authService';
import type { ApiKeyInfo, UserStatsResponse } from '../../types/api';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onKeyChange?: (apiKey: string | null) => void;
}

export default function ApiKeyModal({
  isOpen,
  onClose,
  onKeyChange,
}: ApiKeyModalProps) {
  const [apiKey, setApiKey] = useState<string | null>(authService.getStoredApiKey());
  const [keyInfo, setKeyInfo] = useState<ApiKeyInfo | null>(null);
  const [userStats, setUserStats] = useState<UserStatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Key creation state
  const [newRawKey, setNewRawKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [labelInput, setLabelInput] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);

  // Restore/Paste key state
  const [pasteKeyInput, setPasteKeyInput] = useState<string>('');
  const [isConnecting, setIsConnecting] = useState<boolean>(false);

  const fetchKeyData = async () => {
    const currentKey = authService.getStoredApiKey();
    setApiKey(currentKey);
    if (!currentKey) {
      setKeyInfo(null);
      setUserStats(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [info, stats] = await Promise.all([
        authService.getMe(),
        authService.getStats(),
      ]);
      setKeyInfo(info);
      setUserStats(stats);
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Invalid API key.';
      setError(detail);
      if (err.response?.status === 401) {
        authService.removeStoredApiKey();
        setApiKey(null);
        setKeyInfo(null);
        setUserStats(null);
        if (onKeyChange) onKeyChange(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchKeyData();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleGenerateKey = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsGenerating(true);
    setError(null);
    try {
      const res = await authService.createApiKey(labelInput.trim() || 'Workstation');
      authService.setStoredApiKey(res.api_key);
      setApiKey(res.api_key);
      setNewRawKey(res.api_key);
      setLabelInput('');
      if (onKeyChange) onKeyChange(res.api_key);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate key.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleConnectKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const candidate = pasteKeyInput.trim();
    if (!candidate) return;

    setIsConnecting(true);
    setError(null);
    try {
      authService.setStoredApiKey(candidate);
      const [info, stats] = await Promise.all([
        authService.getMe(),
        authService.getStats(),
      ]);
      setApiKey(candidate);
      setKeyInfo(info);
      setUserStats(stats);
      setPasteKeyInput('');
      if (onKeyChange) onKeyChange(candidate);
    } catch (err: any) {
      authService.removeStoredApiKey();
      setError(err.response?.data?.detail || 'Invalid API key.');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleCopyKey = () => {
    if (!newRawKey) return;
    navigator.clipboard.writeText(newRawKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDisconnectKey = () => {
    authService.removeStoredApiKey();
    setApiKey(null);
    setKeyInfo(null);
    setUserStats(null);
    setNewRawKey(null);
    if (onKeyChange) onKeyChange(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
      <div className="bg-white border border-slate-200 rounded-xl shadow-xl max-w-md w-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-white">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-slate-800">
              Compute Statistics & API Key
            </h2>
            {keyInfo && (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Connected
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 bg-white">
          {error && (
            <div className="p-2.5 text-xs bg-red-50 border border-red-200 text-red-700 rounded-lg">
              {error}
            </div>
          )}

          {/* VIEW 1: Newly Created Key */}
          {newRawKey ? (
            <div className="space-y-3">
              <div className="text-xs text-slate-700">
                <p className="font-semibold text-slate-800 mb-1">
                  Save your API Key
                </p>
                <p className="text-slate-500 text-[11px]">
                  Copy this key now. It will not be shown again.
                </p>
              </div>

              <div className="flex items-center gap-2 p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                <code className="flex-1 font-mono text-xs text-slate-800 break-all select-all">
                  {newRawKey}
                </code>
                <button
                  onClick={handleCopyKey}
                  className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium rounded transition-colors flex items-center gap-1 shrink-0"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      Copy
                    </>
                  )}
                </button>
              </div>

              <button
                onClick={() => {
                  setNewRawKey(null);
                  fetchKeyData();
                }}
                className="w-full py-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold text-xs rounded-lg transition-colors"
              >
                Continue to Compute Statistics
              </button>
            </div>
          ) : apiKey && (keyInfo || userStats) ? (
            /* VIEW 2: Active Key & Compute Statistics */
            <div className="space-y-4">
              {/* Account details */}
              <div className="flex items-center justify-between text-xs pb-3 border-b border-slate-100">
                <div>
                  <span className="font-semibold text-slate-800">
                    {keyInfo?.label || 'API Key'}
                  </span>
                  <span className="ml-2 font-mono text-[11px] text-slate-400">
                    {keyInfo?.key_prefix}
                  </span>
                </div>
                <button
                  onClick={handleDisconnectKey}
                  className="text-[11px] text-red-600 hover:underline font-medium"
                >
                  Disconnect
                </button>
              </div>

              {/* Quota */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs font-medium text-slate-600">
                  <span>Quota Remaining</span>
                  <span className="font-bold text-slate-800">
                    {keyInfo?.quota_remaining ?? 0} / {keyInfo?.quota_limit ?? 100}
                  </span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.max(
                          0,
                          ((keyInfo?.quota_remaining ?? 0) / (keyInfo?.quota_limit || 1)) * 100
                        )
                      )}%`,
                    }}
                  />
                </div>
              </div>

              {/* Statistics Grid */}
              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-slate-700">
                  Compute Statistics
                </span>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-slate-500 text-[11px]">Total Jobs</div>
                    <div className="text-base font-bold text-slate-800 mt-0.5">
                      {userStats?.total_jobs ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-emerald-600 text-[11px]">Successful</div>
                    <div className="text-base font-bold text-slate-800 mt-0.5">
                      {userStats?.success_jobs ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-red-600 text-[11px]">Failed</div>
                    <div className="text-base font-bold text-slate-800 mt-0.5">
                      {userStats?.failed_jobs ?? 0}
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="text-orange-600 text-[11px]">In Progress</div>
                    <div className="text-base font-bold text-slate-800 mt-0.5">
                      {(userStats?.running_jobs ?? 0) + (userStats?.pending_jobs ?? 0)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Refresh */}
              <div className="pt-1 flex justify-end">
                <button
                  onClick={fetchKeyData}
                  disabled={loading}
                  className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-700 font-medium"
                >
                  <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                  Refresh stats
                </button>
              </div>
            </div>
          ) : (
            /* VIEW 3: No Key Configured */
            <div className="space-y-4">
              <p className="text-xs text-slate-600">
                An API key is required to connect to the cluster and track compute jobs.
              </p>

              {/* 1-Click Generate */}
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="Device label (optional)"
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 text-slate-800 placeholder-slate-400 focus:outline-none focus:border-orange-500"
                />
                <button
                  onClick={() => handleGenerateKey()}
                  disabled={isGenerating}
                  className="w-full py-2 bg-orange-600 hover:bg-orange-500 text-white font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
                >
                  {isGenerating && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  Generate API Key
                </button>
              </div>

              <div className="relative flex items-center justify-center py-1">
                <div className="border-t border-slate-200 w-full" />
                <span className="bg-white px-2 text-[10px] text-slate-400 absolute">
                  or connect existing
                </span>
              </div>

              {/* Connect Key */}
              <form onSubmit={handleConnectKey} className="flex gap-2">
                <input
                  type="password"
                  placeholder="Paste af_live_... key"
                  value={pasteKeyInput}
                  onChange={(e) => setPasteKeyInput(e.target.value)}
                  className="flex-1 px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 text-slate-800 placeholder-slate-400 focus:outline-none focus:border-orange-500"
                />
                <button
                  type="submit"
                  disabled={isConnecting || !pasteKeyInput.trim()}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-lg transition-colors disabled:opacity-50"
                >
                  {isConnecting ? '...' : 'Connect'}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
