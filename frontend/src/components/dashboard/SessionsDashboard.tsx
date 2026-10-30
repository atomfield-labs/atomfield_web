import { useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { SessionMetadata, JobStatus } from '../../types/api';
import { jobsService } from '../../api/services';
import { UNTITLED } from '../../hooks/useSessionDraft';
import {
  STATUS_TEXT,
  runStatus,
  statusLook,
  toDisplayStatus,
} from '../../utils/jobStatus';
import StatusIcon from '../StatusIcon';

export type SessionInfo = SessionMetadata;

const NEW_PIPELINE = [
  'h-10 px-4 flex items-center rounded-[10px] bg-orange-700',
  'hover:bg-orange-800 text-sm font-semibold text-white',
].join(' ');
const LIST = [
  'bg-white rounded-xl border border-stone-200 divide-y divide-stone-100',
  'overflow-hidden',
].join(' ');
const ROW_LINK = [
  'flex items-center gap-3 h-14 pl-4 pr-12 hover:bg-stone-50',
  'transition-colors',
].join(' ');
const ROW_DELETE = [
  'absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-stone-400',
  'hover:text-red-700 hover:bg-stone-100 cursor-pointer opacity-0',
  'group-hover:opacity-100 focus-visible:opacity-100',
].join(' ');
const DELETE_ALL = [
  'text-[13px] text-stone-500 hover:text-red-700 cursor-pointer',
].join(' ');
const ROW_TITLE = 'flex-1 min-w-0 truncate text-sm font-medium text-stone-900';
const FACT = 'hidden sm:block shrink-0 text-[13px] text-stone-500';

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
 * One session: how it stands as a small icon, its name, and a few
 * facts; the whole row opens it.
 */
function SessionRow({
  session,
  onDelete,
}: {
  session: SessionInfo;
  onDelete: (event: React.MouseEvent, id: string) => void;
}) {
  const steps = session.nodeCount === 1 ? 'step' : 'steps';
  return (
    <li className="group relative">
      <a href={`#pipeline/${session.id}`} className={ROW_LINK}>
        <StatusIcon status={session.status} />
        <span className={ROW_TITLE}>
          {session.title}
        </span>
        <span className={`${FACT} w-24`}>
          {STATUS_TEXT[statusLook(session.status)]}
        </span>
        <span className={`${FACT} w-16`}>
          {session.nodeCount > 0 && `${session.nodeCount} ${steps}`}
        </span>
        <span className={`${FACT} w-32`}>{shownDate(session.updatedAt)}</span>
      </a>
      <button
        type="button"
        onClick={(event) => onDelete(event, session.id)}
        aria-label={`Delete ${session.title}`}
        className={ROW_DELETE}
      >
        <Trash2 size={15} />
      </button>
    </li>
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
    <div className="w-full min-h-screen bg-stone-50 px-6 pt-24 pb-16">
      <div className="max-w-4xl mx-auto">
        <header className="flex items-center justify-between gap-4 mb-5">
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Sessions
          </h1>
          <a href="#pipeline/new" className={NEW_PIPELINE}>
            New pipeline
          </a>
        </header>
        {sessions.length === 0 ? (
          <p className="py-20 text-center text-stone-500">No sessions yet.</p>
        ) : (
          <>
            <ul className={LIST}>
              {sessions.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  onDelete={handleDeleteSession}
                />
              ))}
            </ul>
            <div className="mt-3 text-right">
              <button
                type="button"
                onClick={handleClearAllSessions}
                className={DELETE_ALL}
              >
                Delete all
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
