import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Download } from 'lucide-react';
import { jobsService } from '../../api/services';
import { useJobFiles } from '../../hooks/useJobFiles';
import { triggerFileDownload } from '../../utils/downloadHelper';

// A long file shows its start; Download has all of it.
const SHOWN_CHARACTERS = 200 * 1024;
const SUMMARY = /summary/i;

const ROW = [
  'w-full text-left px-2.5 py-1.5 rounded-md text-xs font-mono truncate',
  'transition-colors cursor-pointer',
].join(' ');
const ROW_IDLE = 'text-slate-600 hover:text-orange-600';
const ROW_CHOSEN = 'bg-orange-50 text-orange-600';
const VIEWER = [
  'flex-1 min-h-0 bg-slate-50 border border-slate-200 rounded-lg p-4',
  'font-mono text-xs text-slate-800 overflow-auto leading-relaxed',
  'whitespace-pre select-text',
].join(' ');
const DOWNLOAD = [
  'py-1 px-2.5 border border-slate-200 bg-white hover:bg-slate-100',
  'text-slate-600 text-xs font-medium rounded-lg transition-colors',
  'flex items-center gap-1.5 cursor-pointer shadow-2xs',
  'disabled:opacity-50 disabled:cursor-default',
].join(' ');
const MUTED = 'text-slate-400';

interface JobArtifactsProps {
  jobId: string | undefined;
  status: string | undefined;
}

interface Reading {
  name: string;
  text: string | null;
}

/**
 * A job's text files: their names on the left, the one chosen on the
 * right. A summary comes first, as what a person most wants to read.
 */
export default function JobArtifacts({ jobId, status }: JobArtifactsProps) {
  const { files, others } = useJobFiles(jobId, status);
  const [chosen, setChosen] = useState<string | null>(null);
  const [reading, setReading] = useState<Reading | null>(null);

  const names = useMemo(() => {
    const texts = files.filter((file) => file.kind === 'text');
    const sorted = texts.map((file) => file.name).sort();
    return [
      ...sorted.filter((name) => SUMMARY.test(name)),
      ...sorted.filter((name) => !SUMMARY.test(name)),
    ];
  }, [files]);

  const shown = chosen && names.includes(chosen) ? chosen : names[0];

  useEffect(() => {
    if (!jobId || !shown) return;
    let active = true;
    jobsService
      .readJobFile(jobId, shown)
      .then((text) => active && setReading({ name: shown, text }))
      .catch(() => active && setReading({ name: shown, text: null }));
    return () => {
      active = false;
    };
  }, [jobId, shown, status]);

  if (names.length === 0 && others === 0) {
    return <p className={`text-xs ${MUTED}`}>No artifacts yet.</p>;
  }

  const current = reading?.name === shown ? reading : null;
  const text = current?.text ?? '';
  const isCut = text.length > SHOWN_CHARACTERS;
  let body: ReactNode = <span className={MUTED}>Loading...</span>;
  if (current) {
    body =
      current.text === null ? (
        <span className={MUTED}>Could not read this file.</span>
      ) : (
        text.slice(0, SHOWN_CHARACTERS)
      );
  }

  return (
    <div className="h-full flex gap-3 min-h-0">
      <div className="w-56 shrink-0 flex flex-col gap-2 min-h-0">
        <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-0.5">
          {names.map((name) => (
            <button
              key={name}
              type="button"
              title={name}
              className={`${ROW} ${name === shown ? ROW_CHOSEN : ROW_IDLE}`}
              onClick={() => setChosen(name)}
            >
              {name}
            </button>
          ))}
        </div>
        {others > 0 && (
          <p className={`text-[11px] leading-snug px-2.5 ${MUTED}`}>
            {others} more stay on the computer that ran it
          </p>
        )}
      </div>

      {shown && (
        <div className="flex-1 min-w-0 flex flex-col gap-2">
          <div className={VIEWER}>{body}</div>
          <div className="flex items-center justify-end gap-3 shrink-0">
            {isCut && (
              <span className={`text-[11px] ${MUTED}`}>
                Showing the start; Download has the rest
              </span>
            )}
            <button
              type="button"
              className={DOWNLOAD}
              disabled={!current?.text}
              onClick={() => triggerFileDownload(text, shown)}
            >
              <Download className="w-3.5 h-3.5 text-slate-500" />
              <span>Download</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
