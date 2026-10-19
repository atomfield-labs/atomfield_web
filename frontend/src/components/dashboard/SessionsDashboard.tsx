import { useEffect, useState } from 'react';
import type { SessionMetadata, JobStatus } from '../../types/api';
import { jobsService } from '../../api/services';
import { authService } from '../../api/services/authService';
import ApiKeyModal from '../auth/ApiKeyModal';

export type SessionInfo = SessionMetadata;

export default function SessionsDashboard() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [apiKey, setApiKey] = useState<string | null>(authService.getStoredApiKey());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  const refreshKeyInfo = async () => {
    const currentKey = authService.getStoredApiKey();
    setApiKey(currentKey);
    if (!currentKey) {
      setIsAuthenticated(false);
      return;
    }

    try {
      const info = await authService.getMe();
      setIsAuthenticated(Boolean(info && info.is_active));
    } catch {
      setIsAuthenticated(false);
    }
  };

  useEffect(() => {
    refreshKeyInfo();
  }, [apiKey]);

  useEffect(() => {
    let isSubscribed = true;
    let loadedSessions: SessionInfo[] = [];

    const saved = localStorage.getItem('atomfield_sessions');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          loadedSessions = parsed
            .filter((item: any) => {
              const id = typeof item === 'string' ? item : item?.id;
              // Template card has its own dedicated card, exclude template ID from user sessions
              return id && id !== 'nanoreactor';
            })
            .map((item: any) => {
              if (typeof item === 'string') {
                return {
                  id: item,
                  title: item.startsWith('nanoreactor')
                    ? 'Nanoreactor Catalysis'
                    : `Session ${item.substring(0, 8)}`,
                  status: 'Draft' as JobStatus,
                  nodeCount: 0,
                  updatedAt: 'Recent',
                };
              }
              return item;
            });

          // Ensure uniqueness: exactly one card per session ID
          const uniqueMap = new Map<string, SessionInfo>();
          loadedSessions.forEach((s) => uniqueMap.set(s.id, s));
          setSessions(Array.from(uniqueMap.values()));
        }
      } catch (e) {
        console.error('Failed to parse sessions', e);
      }
    }

    const syncLiveJobStatuses = async () => {
      try {
        const { jobs } = await jobsService.listJobs({ limit: 40 });
        if (!isSubscribed) return;

        setSessions((prevSessions) => {
          let updatedList = [...prevSessions];
          let hasChanges = false;

          // If a cluster job has a pipeline_id not in sessions, add it as a session
          jobs.forEach((job) => {
            const pipelineId = job.parameters?.pipeline_id;
            if (
              pipelineId &&
              pipelineId !== 'nanoreactor' &&
              !updatedList.some((s) => s.id === pipelineId)
            ) {
              const newSession: SessionInfo = {
                id: pipelineId,
                title: pipelineId.startsWith('nanoreactor')
                  ? 'Nanoreactor Catalysis'
                  : `Session ${pipelineId.substring(0, 8)}`,
                status: job.status,
                nodeCount: 1,
                updatedAt: job.created_at,
              };
              updatedList.unshift(newSession);
              hasChanges = true;
            }
          });

          // Sync status for existing sessions from cluster jobs
          updatedList = updatedList.map((s) => {
            const matchingJob = jobs.find(
              (j) => j.parameters?.pipeline_id === s.id
            );
            if (matchingJob && matchingJob.status !== s.status) {
              hasChanges = true;
              return { ...s, status: matchingJob.status };
            }
            return s;
          });

          if (hasChanges) {
            try {
              // Deduplicate by ID
              const deduplicated = Array.from(
                new Map(updatedList.map((item) => [item.id, item])).values()
              );
              localStorage.setItem(
                'atomfield_sessions',
                JSON.stringify(deduplicated)
              );
              return deduplicated;
            } catch (err) {
              console.error('Failed to update sessions in storage', err);
            }
          }
          return prevSessions;
        });
      } catch (err) {
        console.error('Failed to sync live job statuses in sessions', err);
      }
    };

    syncLiveJobStatuses();
    const interval = setInterval(syncLiveJobStatuses, 3500);

    return () => {
      isSubscribed = false;
      clearInterval(interval);
    };
  }, [apiKey]);

  const handleDeleteSession = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this session?')) return;

    try {
      const filtered = sessions.filter((s) => s.id !== id);
      setSessions(filtered);
      localStorage.setItem('atomfield_sessions', JSON.stringify(filtered));
      localStorage.removeItem(`atomfield_blueprint_${id}`);
    } catch (err) {
      console.error('Failed to delete session', err);
    }
  };

  const handleClearAllSessions = async () => {
    if (
      !confirm(
        'Are you sure you want to clear all sessions and database records? This cannot be undone.'
      )
    ) {
      return;
    }

    try {
      await jobsService.clearAllJobs();
    } catch (err) {
      console.error('Failed to clear database jobs', err);
    }

    try {
      localStorage.removeItem('atomfield_sessions');
      Object.keys(localStorage).forEach((key) => {
        if (
          key.startsWith('atomfield_blueprint_') ||
          key.startsWith('atomfield_jobs_')
        ) {
          localStorage.removeItem(key);
        }
      });
      setSessions([]);
    } catch (err) {
      console.error('Failed to clear local sessions', err);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Running':
      case 'Pending':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-orange-50 text-orange-700 text-xs font-bold rounded-md font-mono border border-orange-300">
            <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
            RUNNING
          </span>
        );
      case 'Success':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-md font-mono border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            SUCCESS
          </span>
        );
      case 'Failed':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-red-50 text-red-700 text-xs font-bold rounded-md font-mono border border-red-200">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            FAILED
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-slate-50 text-slate-600 text-xs font-bold rounded-md font-mono border border-slate-200">
            <span className="w-2 h-2 rounded-full bg-slate-400" />
            DRAFT
          </span>
        );
    }
  };

  const formatDate = (isoString: string) => {
    if (!isoString || isoString === 'Recent') return 'Just now';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Recent';
    }
  };

  return (
    <>
      <div className="w-full min-h-screen bg-slate-50 p-8 pt-24">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8 gap-4">
            <div>
              <h1 className="text-3xl font-extrabold text-slate-800 mb-2">Sessions</h1>
              <p className="text-slate-500">
                Manage and review your calculation pipelines and sessions.
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* Server Connection Status */}
              {isAuthenticated ? (
                <button
                  onClick={() => setIsApiKeyModalOpen(true)}
                  title="Server Connected — View Compute Statistics"
                  className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5 cursor-pointer hover:bg-emerald-100 transition-colors"
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span>Connected</span>
                </button>
              ) : (
                <button
                  onClick={() => setIsApiKeyModalOpen(true)}
                  title="Server Disconnected — Click to connect API Key"
                  className="px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200 flex items-center gap-1.5 cursor-pointer hover:bg-red-100 transition-colors"
                >
                  <span className="w-2 h-2 rounded-full bg-red-500" />
                  <span>Disconnected</span>
                </button>
              )}

              {sessions.length > 0 && (
                <button
                  onClick={handleClearAllSessions}
                  className="px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5"
                >
                  <svg
                    className="w-4 h-4 text-red-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                  Clear All Sessions
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* New Pipeline Card */}
            <a
              href="#pipeline/new"
              className="flex flex-col items-center justify-center border-2 border-dashed border-orange-200 rounded-xl p-8 hover:border-orange-500 hover:bg-orange-50/40 transition-colors group cursor-pointer min-h-[220px]"
            >
              <div className="w-12 h-12 rounded-full bg-orange-50 flex items-center justify-center group-hover:bg-orange-100 mb-4 transition-colors">
                <span className="text-2xl text-orange-400 group-hover:text-orange-600 font-bold">+</span>
              </div>
              <h3 className="text-lg font-bold text-slate-700 group-hover:text-orange-700">
                New Pipeline
              </h3>
              <p className="text-sm text-slate-500 text-center mt-2 group-hover:text-orange-600/80">
                Start assembling a new calculation graph.
              </p>
            </a>

            {/* Prebuilt Nanoreactor Demo Card (Template) */}
            <a
              href="#pipeline/nanoreactor"
              className="flex flex-col bg-white border border-orange-200 rounded-xl p-6 hover:shadow-lg hover:border-orange-400 transition-all cursor-pointer min-h-[220px] relative overflow-hidden group border-t-4 border-t-orange-500"
            >
              <div className="flex justify-between items-start mb-4">
                <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-orange-50 text-orange-700 text-xs font-bold rounded-md font-mono border border-orange-200">
                  <span className="w-2 h-2 rounded-full bg-orange-500" />
                  PREBUILT
                </span>
              </div>
              <h3 className="text-lg font-bold text-slate-800 mb-1 group-hover:text-orange-600 transition-colors">
                Nanoreactor Catalysis
              </h3>
              <p className="text-sm text-slate-500 mb-4">
                Automated transition state search & turnover frequencies.
              </p>

              <div className="mt-auto flex justify-between items-center text-xs text-slate-400 font-medium border-t border-slate-100 pt-3">
                <span>1 Script</span>
                <span className="text-orange-600 font-semibold group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
                  Explore Graph
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                </span>
              </div>
            </a>

            {/* User Session Cards */}
            {sessions.map((s) => (
              <a
                key={s.id}
                href={`#pipeline/${s.id}`}
                className="flex flex-col bg-white border border-orange-200 rounded-xl p-6 hover:shadow-lg hover:border-orange-400 transition-all cursor-pointer min-h-[220px] relative overflow-hidden group border-t-4 border-t-orange-500"
              >
                <div className="flex justify-between items-start mb-4">
                  {getStatusBadge(s.status)}
                  <button
                    type="button"
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    title="Delete"
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-all"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                </div>

                <h3 className="text-lg font-bold text-slate-800 mb-1 group-hover:text-orange-600 transition-colors line-clamp-1">
                  {s.title}
                </h3>
                <p className="text-xs text-slate-400 font-mono mb-4">
                  ID: {s.id.substring(0, 16)}
                </p>

                <div className="mt-auto flex justify-between items-center text-xs text-slate-400 font-medium border-t border-slate-100 pt-3">
                  <span className="font-semibold text-slate-600">
                    {s.nodeCount} {s.nodeCount === 1 ? 'Node' : 'Nodes'} • {formatDate(s.updatedAt)}
                  </span>
                  <span className="text-orange-600 font-semibold group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
                    Open Pipeline
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M14 5l7 7m0 0l-7 7m7-7H3"
                      />
                    </svg>
                  </span>
                </div>
              </a>
            ))}
          </div>
        </div>
      </div>

      <ApiKeyModal
        isOpen={isApiKeyModalOpen}
        onClose={() => {
          setIsApiKeyModalOpen(false);
          refreshKeyInfo();
        }}
        onKeyChange={(newKey) => {
          setApiKey(newKey);
          refreshKeyInfo();
        }}
      />
    </>
  );
}
