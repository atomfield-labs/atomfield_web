import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { SessionSummary } from '../../types/api';
import { jobsService, sessionsService } from '../../api/services';
import { useSignedInAccount } from '../../hooks/useAccount';
import { UNTITLED } from '../../hooks/useSessionDraft';
import { useWorkflows } from '../../hooks/useWorkflows';
import {
  STATUS_TEXT,
  statusLook,
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

const POLL_MS = 3500;

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
 * A session's time as people read it.
 */
function shownDate(when: string): string {
  return new Date(when).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * A session's size and date, on one line.
 */
function shownFacts(session: SessionSummary): string {
  const when = shownDate(session.updated_at);
  if (session.node_count === 0) return when;
  const steps = session.node_count === 1 ? 'step' : 'steps';
  return `${session.node_count} ${steps} · ${when}`;
}

/**
 * One session: how it stands, its name, its size and date. The whole
 * card opens it; the cross shows on hover.
 */
function SessionCard({
  session,
  onDelete,
}: {
  session: SessionSummary;
  onDelete: (event: React.MouseEvent, id: string) => void;
}) {
  const look = statusLook(session.state);
  const title = session.title || UNTITLED;
  return (
    <div className="group relative">
      <a href={`#pipeline/${session.id}`} className={CARD}>
        <span className={CARD_STATUS}>
          <span className={`w-2 h-2 rounded-full ${DOT_COLOUR[look]}`} />
          {STATUS_TEXT[look]}
        </span>
        <h3 className={CARD_TITLE}>{title}</h3>
        <p className={CARD_FACTS}>{shownFacts(session)}</p>
      </a>
      <button
        type="button"
        onClick={(event) => onDelete(event, session.id)}
        aria-label={`Delete ${title}`}
        className={CARD_DELETE}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export default function SessionsDashboard() {
  const account = useSignedInAccount();
  const workflows = useWorkflows();
  const hasNone = account.role !== 'owner' && workflows?.length === 0;
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  // Runs move on by themselves, so keep looking.
  useEffect(() => {
    let active = true;
    const load = () =>
      sessionsService
        .list()
        .then((found) => {
          if (active) setSessions(found);
        })
        .catch((err) => console.error('Failed to load sessions', err));
    void load();
    const interval = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this session?')) return;
    setSessions((list) => list.filter((session) => session.id !== id));
    try {
      await jobsService.deleteSession(id);
    } catch (err) {
      console.error('Failed to delete session', err);
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
      setSessions([]);
    } catch (err) {
      console.error('Failed to delete your sessions', err);
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
