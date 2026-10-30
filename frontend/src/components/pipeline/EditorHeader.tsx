import { useState, type FormEvent } from 'react';
import { ArrowLeft } from 'lucide-react';
import RunOnPicker from './RunOnPicker';
import StatusIcon from '../StatusIcon';
import { useAccount } from '../../hooks/useAccount';
import type { SaveStatus } from '../../types/api';
import type { RunProgress } from '../../utils/jobStatus';

interface EditorHeaderProps {
  title: string;
  onRename: (title: string) => void;
  saveStatus: SaveStatus;
  progress: RunProgress;
  isStarting: boolean;
  onRun: () => void;
  onStop: () => void;
  // Where the pipeline runs; null means the shared AtomField server.
  targetId: string | null;
  onTargetChange: (targetId: string | null) => void;
}

const HEADER = [
  'relative flex flex-wrap items-center justify-between gap-x-4 gap-y-2',
  'px-3 py-2 bg-white border-b border-stone-200 shrink-0 z-10',
].join(' ');
const ICON_LINK = [
  'flex items-center justify-center w-10 h-10 rounded-[10px]',
  'text-stone-600 hover:bg-stone-100',
].join(' ');
const PRIMARY = [
  'h-10 px-5 rounded-[10px] bg-orange-700 hover:bg-orange-800 text-white',
  'text-sm font-semibold cursor-pointer disabled:cursor-not-allowed',
  'disabled:bg-stone-100 disabled:text-stone-400',
].join(' ');
const SECONDARY = [
  'h-10 px-4 rounded-[10px] border border-stone-200 bg-white text-sm',
  'font-medium text-stone-900 hover:bg-stone-50 cursor-pointer',
].join(' ');
const TITLE = 'truncate text-[15px] font-semibold text-stone-900 cursor-text';
const TITLE_INPUT = [
  'h-8 w-64 px-2 rounded-md border border-stone-300 text-[15px]',
  'font-semibold focus:outline-none focus:border-orange-700',
].join(' ');
const INITIALS = [
  'flex items-center justify-center w-10 h-10 rounded-full',
  'bg-stone-900 text-white text-[13px] font-semibold',
].join(' ');
const STATUS_LINE = 'ml-2 flex items-center gap-1.5 text-[13px] text-stone-600';

// How a finished run is shown: its words, and a step status for its icon.
const ENDINGS = {
  done: { text: 'Done', status: 'Success' },
  failed: { text: 'Failed', status: 'Failed' },
  cancelled: { text: 'Cancelled', status: 'Cancelled' },
} as const;

function RunStatus({ progress }: { progress: RunProgress }) {
  if (progress.phase === 'idle') return null;
  if (progress.phase === 'running') {
    return (
      <span className={STATUS_LINE}>
        <span
          aria-hidden="true"
          className="w-[7px] h-[7px] rounded-full bg-blue-600"
        />
        Running · {progress.done} of {progress.total}
      </span>
    );
  }
  const ending = ENDINGS[progress.phase];
  return (
    <span className={STATUS_LINE}>
      <StatusIcon status={ending.status} size={14} />
      {ending.text}
    </span>
  );
}

function ProgressLine({ progress }: { progress: RunProgress }) {
  const share = progress.total ? progress.done / progress.total : 0;
  return (
    <div
      aria-hidden="true"
      className="absolute left-0 right-0 -bottom-px h-0.5 bg-stone-100"
    >
      <div
        className="h-full bg-blue-600 transition-[width] duration-500"
        style={{ width: `${Math.round(share * 100)}%` }}
      />
    </div>
  );
}

/**
 * The pipeline's name; click it to rename.
 */
function Title({
  title,
  onRename,
}: {
  title: string;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  if (editing === null) {
    return (
      <button
        type="button"
        onClick={() => setEditing(title)}
        title="Rename"
        className={TITLE}
      >
        {title}
      </button>
    );
  }
  const save = (event?: FormEvent) => {
    event?.preventDefault();
    onRename(editing);
    setEditing(null);
  };
  return (
    <form onSubmit={save}>
      <input
        autoFocus
        value={editing}
        onChange={(event) => setEditing(event.target.value)}
        onBlur={() => save()}
        onKeyDown={(event) => event.key === 'Escape' && setEditing(null)}
        maxLength={100}
        aria-label="Pipeline name"
        className={TITLE_INPUT}
      />
    </form>
  );
}

/**
 * The signed-in person's initials, leading to their account.
 */
function Initials() {
  const { state } = useAccount();
  if (state.status !== 'signed-in') return null;
  const name = state.account.label || state.account.email || '?';
  const words = name.split(/\s+/).filter(Boolean);
  const letters = words.map((word) => word[0]).join('').slice(0, 2);
  return (
    <a
      href="#account"
      aria-label="Your account"
      title={name}
      className={INITIALS}
    >
      {letters.toUpperCase()}
    </a>
  );
}

/**
 * The editor's bar: back, the pipeline's name and how its run stands;
 * where it runs; Run (or Stop while it runs); your account.
 */
export default function EditorHeader({
  title,
  onRename,
  saveStatus,
  progress,
  isStarting,
  onRun,
  onStop,
  targetId,
  onTargetChange,
}: EditorHeaderProps) {
  const running = progress.phase === 'running';
  return (
    <header className={HEADER}>
      <div className="flex items-center gap-1.5 min-w-0">
        <a
          href="#dashboard"
          aria-label="Back to sessions"
          className={ICON_LINK}
        >
          <ArrowLeft size={18} />
        </a>
        <Title title={title} onRename={onRename} />
        <RunStatus progress={progress} />
        {saveStatus === 'saving' && (
          <span className="ml-2 text-xs text-stone-400">Saving…</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <RunOnPicker value={targetId} onChange={onTargetChange} />
        {running ? (
          <button type="button" onClick={onStop} className={SECONDARY}>
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onRun}
            disabled={isStarting || progress.total === 0}
            className={PRIMARY}
          >
            {isStarting ? 'Starting…' : 'Run'}
          </button>
        )}
        <Initials />
      </div>
      {running && <ProgressLine progress={progress} />}
    </header>
  );
}
