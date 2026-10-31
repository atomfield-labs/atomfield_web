import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { SessionMetadata, JobStatus } from '../../types/api';
import { jobsService } from '../../api/services';
import { useSignedInAccount } from '../../hooks/useAccount';
import { UNTITLED } from '../../hooks/useSessionDraft';
import { useWorkflows } from '../../hooks/useWorkflows';
import {
  STATUS_TEXT,
  runStatus,
  statusLook,
  toDisplayStatus,
  type StatusLook,
} from '../../utils/jobStatus';
import {
  CARD,
  CARD_FACTS,
  CARD_GRID,
  CARD_TITLE,
  NEW_CARD,
  NEW_CARD_PLUS,
  NEW_CARD_SIGN,
  NEW_CARD_TITLE,
  ON_HOVER,
  PAGE,
  PAGE_TITLE,
  PAGE_WIDTH,
} from './cardStyle';

export type SessionInfo = SessionMetadata;

const DOT_COLOUR: Record<StatusLook, string> = {
  none: 'bg-slate-300',
  waiting: 'bg-slate-400',
  running: 'bg-orange-500 animate-pulse',
  done: 'bg-emerald-500',
  failed: 'bg-red-500',
  stopped: 'bg-slate-400',
};

const CARD_STATUS = 'flex items-center gap-1.5 mb-3 text-xs text-slate-600';
const CARD_DELETE = [
  'absolute top-4 right-4 p-1.5 rounded-md text-slate-400',
  'hover:text-red-600 hover:bg-red-50 transition-all cursor-pointer',
  ON_HOVER,
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
  const account = useSignedInAccount();
  const workflows = useWorkflows();
  const hasNone = account.role !== 'owner' && workflows?.length === 0;
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
    <div className={PAGE}>
      <div className={PAGE_WIDTH}>
        <div className="flex items-center justify-between gap-4 mb-8">
          <h1 className={PAGE_TITLE}>Sessions</h1>
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

        {hasNone && (
          <p className="mb-6 text-sm text-slate-500">
            No workflows yet. Ask your lab admin.
          </p>
        )}
        <div className={CARD_GRID}>
          {!hasNone && (
            <a href="#pipeline/new" className={NEW_CARD}>
              <div className={NEW_CARD_PLUS}>
                <span className={NEW_CARD_SIGN}>+</span>
              </div>
              <h3 className={NEW_CARD_TITLE}>New pipeline</h3>
            </a>
          )}

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
