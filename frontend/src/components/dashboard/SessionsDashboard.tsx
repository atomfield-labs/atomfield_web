import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { SessionMetadata, JobStatus } from '../../types/api';
import { jobsService } from '../../api/services';
import { UNTITLED } from '../../hooks/useSessionDraft';
import {
  STATUS_TEXT,
  runStatus,
  statusLook,
  toDisplayStatus,
  type StatusLook,
} from '../../utils/jobStatus';

export type SessionInfo = SessionMetadata;

const DOT_COLOUR: Record<StatusLook, string> = {
  none: 'bg-slate-300',
  waiting: 'bg-slate-400',
  running: 'bg-orange-500 animate-pulse',
  done: 'bg-emerald-500',
  failed: 'bg-red-500',
  stopped: 'bg-slate-400',
};

const NEW_CARD = [
  'flex flex-col items-center justify-center min-h-[160px] p-6 group',
  'border-2 border-dashed border-orange-200 rounded-xl cursor-pointer',
  'hover:border-orange-500 hover:bg-orange-50/40 transition-colors',
].join(' ');
const NEW_CARD_PLUS = [
  'w-12 h-12 mb-3 rounded-full bg-orange-50 group-hover:bg-orange-100',
  'flex items-center justify-center transition-colors',
].join(' ');
const NEW_CARD_SIGN =
  'text-2xl font-bold text-orange-400 group-hover:text-orange-600';
const NEW_CARD_TITLE = [
  'text-lg font-bold text-slate-700 group-hover:text-orange-600',
  'transition-colors',
].join(' ');
const CARD = [
  'flex flex-col h-full min-h-[160px] p-6 bg-white rounded-xl',
  'border border-slate-200 group-hover:border-orange-400',
  'transition-colors',
].join(' ');
const CARD_STATUS = 'flex items-center gap-1.5 mb-3 text-xs text-slate-600';
const CARD_TITLE = [
  'mb-4 text-lg font-bold text-slate-800 group-hover:text-orange-600',
  'transition-colors line-clamp-1',
].join(' ');
const CARD_FACTS = [
  'mt-auto pt-3 border-t border-slate-100 text-xs font-medium',
  'text-slate-500',
].join(' ');
const CARD_DELETE = [
  'absolute top-4 right-4 p-1.5 rounded-md text-slate-400',
  'hover:text-red-600 hover:bg-red-50 transition-all cursor-pointer',
  'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
  'pointer-coarse:opacity-100',
].join(' ');
const DELETE_ALL =
  'text-[13px] text-slate-500 hover:text-red-600 cursor-pointer';

/**
 * Sessions saved before pipelines had names carry a made-up one.
 */
function withoutMadeUpName(session: SessionInfo): SessionInfo {
  const madeUp = !session.named && session.title?.startsWith('Session ');
  return madeUp ? { ...session, title: UNTITLED } : session;
}

/**
 * A session's time as people read it.
 */
function shownDate(when: string): string {
  if (!when || when === 'Recent') return 'Just now';
  const date = new Date(when);
  if (Number.isNaN(date.getTime())) return 'Recent';
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * A session's size and date, on one line.
 */
function shownFacts(session: SessionInfo): string {
  const when = shownDate(session.updatedAt);
  if (session.nodeCount === 0) return when;
  const steps = session.nodeCount === 1 ? 'step' : 'steps';
  return `${session.nodeCount} ${steps} · ${when}`;
}

/**
 * One session: how it stands, its name, its size and date. The whole
 * card opens it; the cross shows on hover.
 */
function SessionCard({
  session,
  onDelete,
}: {
  session: SessionInfo;
  onDelete: (event: React.MouseEvent, id: string) => void;
}) {
  const look = statusLook(session.status);
  return (
    <div className="group relative">
      <a href={`#pipeline/${session.id}`} className={CARD}>
        <span className={CARD_STATUS}>
          <span className={`w-2 h-2 rounded-full ${DOT_COLOUR[look]}`} />
          {STATUS_TEXT[look]}
        </span>
        <h3 className={CARD_TITLE}>{session.title}</h3>
        <p className={CARD_FACTS}>{shownFacts(session)}</p>
      </a>
      <button
        type="button"
        onClick={(event) => onDelete(event, session.id)}
        aria-label={`Delete ${session.title}`}
        className={CARD_DELETE}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

const getDeletedSessionIds = (): Set<string> => {
  try {
    const raw = localStorage.getItem('atomfield_deleted_sessions');
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
};

const markSessionDeleted = (id: string) => {
  try {
    const deleted = getDeletedSessionIds();
    deleted.add(id);
    localStorage.setItem(
      'atomfield_deleted_sessions',
      JSON.stringify(Array.from(deleted))
    );
  } catch (err) {
    console.error('Failed to mark session deleted in storage', err);
  }
};

export default function SessionsDashboard() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  useEffect(() => {
    let isSubscribed = true;
    let loadedSessions: SessionInfo[] = [];

    const saved = localStorage.getItem('atomfield_sessions');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          const deletedIds = getDeletedSessionIds();
          loadedSessions = parsed
            .filter((item: any) => {
              const id = typeof item === 'string' ? item : item?.id;
              return id && !deletedIds.has(id);
            })
            .map((item: any) => {
              if (typeof item === 'string') {
                return {
                  id: item,
                  title: UNTITLED,
                  status: 'Draft' as JobStatus,
                  nodeCount: 0,
                  updatedAt: 'Recent',
                };
              }
              return withoutMadeUpName(item);
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

          const deletedIds = getDeletedSessionIds();

          // If a cluster job has a pipeline_id not in sessions, add it as a session
          jobs.forEach((job) => {
            const pipelineId = job.parameters?.pipeline_id;
            if (
              pipelineId &&
              !deletedIds.has(pipelineId) &&
              !updatedList.some((s) => s.id === pipelineId)
            ) {
              const newSession: SessionInfo = {
                id: pipelineId,
                title: UNTITLED,
                status: toDisplayStatus(job.status),
                nodeCount: 1,
                updatedAt: job.created_at,
              };
              updatedList.unshift(newSession);
              hasChanges = true;
            }
          });

          // A session's status and size, read from all its jobs.
          updatedList = updatedList.map((s) => {
            const own = jobs.filter((j) => j.parameters?.pipeline_id === s.id);
            if (own.length === 0) return s;
            const status = runStatus(own.map((j) => toDisplayStatus(j.status)));
            const nodeCount = Math.max(s.nodeCount, own.length);
            if (status === s.status && nodeCount === s.nodeCount) return s;
            hasChanges = true;
            return { ...s, status, nodeCount };
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
  }, []);

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this session?')) return;

    markSessionDeleted(id);

    try {
      const filtered = sessions.filter((s) => s.id !== id);
      setSessions(filtered);
      localStorage.setItem('atomfield_sessions', JSON.stringify(filtered));
      localStorage.removeItem(`atomfield_blueprint_${id}`);
      localStorage.removeItem(`atomfield_jobs_${id}`);
    } catch (err) {
      console.error('Failed to delete session locally', err);
    }

    try {
      await jobsService.deleteSession(id);
    } catch (err) {
      console.error('Failed to delete session on cluster', err);
    }
  };

  const handleClearAllSessions = async () => {
    if (
      !confirm(
        'Delete all of your sessions, jobs and files? ' +
          'Other users are not affected. This cannot be undone.'
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
      localStorage.removeItem('atomfield_deleted_sessions');
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

  return (
    <div className="w-full min-h-screen bg-slate-50 p-8 pt-24">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between gap-4 mb-8">
          <h1 className="text-3xl font-extrabold text-slate-800">Sessions</h1>
          {sessions.length > 0 && (
            <button
              type="button"
              onClick={handleClearAllSessions}
              className={DELETE_ALL}
            >
              Delete all
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <a href="#pipeline/new" className={NEW_CARD}>
            <div className={NEW_CARD_PLUS}>
              <span className={NEW_CARD_SIGN}>+</span>
            </div>
            <h3 className={NEW_CARD_TITLE}>New pipeline</h3>
          </a>

          {sessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onDelete={handleDeleteSession}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
