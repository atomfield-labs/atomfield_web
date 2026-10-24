import { useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';
import { API_BASE } from '../../api/client';
import { jobsService } from '../../api/services';
import type { BundleInfo } from '../../types/api';

// A zip on its way: keep asking until it is ready (about 2 minutes).
const WAITING = new Set(['requested', 'packing']);
const POLL_MS = 2000;
const MAX_POLLS = 60;
const GIGABYTE = 1024 ** 3;
const COMMAND = 'flex-1 p-2 bg-slate-50 rounded font-mono break-all';
const SPINNER = [
  'w-3.5 h-3.5 border-2 border-orange-500 border-t-transparent',
  'rounded-full animate-spin',
].join(' ');

const BUTTON = [
  'py-1.5 px-3 border border-slate-200 bg-white hover:bg-orange-50',
  'hover:border-orange-200 text-slate-700 hover:text-orange-600 text-xs',
  'font-semibold rounded-lg transition-colors shadow-2xs flex',
  'items-center gap-1.5 cursor-pointer disabled:opacity-50',
].join(' ');
const PANEL = [
  'absolute bottom-full right-0 mb-2 w-96 max-w-[90vw] p-3 bg-white',
  'border border-slate-200 rounded-lg shadow-lg text-xs text-slate-700',
  'space-y-2',
].join(' ');

/**
 * Turn a link from the API into one the browser can open: the server's
 * own store gives paths, a cloud store full URLs.
 */
function absolute(url: string): string {
  return url.startsWith('http') ? url : `${API_BASE}${url}`;
}

/**
 * Wait the given time.
 */
function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get a run's files: download its zip when there is one, otherwise
 * show where the files are (with a command to copy them) and offer
 * to make a download link.
 */
export default function RunFilesButton({ runId }: { runId: string | null }) {
  const [info, setInfo] = useState<BundleInfo | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  // The signed link carries its own permission: the browser simply
  // opens it, no API key involved, and saves what it serves.
  const download = (current: BundleInfo) => {
    if (current.download_url) {
      window.location.assign(absolute(current.download_url));
    }
  };

  const waitForZip = async (id: string) => {
    setMessage('Preparing the zip...');
    for (let poll = 0; poll < MAX_POLLS; poll += 1) {
      const current = await jobsService.getBundle(id);
      setInfo(current);
      if (current.status === 'ready') {
        setMessage(null);
        return download(current);
      }
      if (!WAITING.has(current.status)) {
        return setMessage(describe(current));
      }
      await pause(POLL_MS);
    }
    setMessage('The zip is taking a while; try again in a minute.');
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch {
      setMessage('Could not reach the server.');
    } finally {
      setBusy(false);
    }
  };

  const fetchFiles = () =>
    run(async () => {
      if (!runId) return setMessage('Run the pipeline first.');
      const current = await jobsService.getBundle(runId);
      setInfo(current);
      if (!current.finished) return setMessage('The run is still going.');
      if (current.status === 'ready') return download(current);
      if (WAITING.has(current.status)) return waitForZip(runId);
      // Our own machine ran it (no folder to show): make the zip again.
      if (!current.folder && current.status !== 'too_big') {
        await jobsService.requestBundle(runId);
        return waitForZip(runId);
      }
      setMessage(describe(current));
    });

  const makeLink = () =>
    run(async () => {
      if (!runId) return;
      setInfo(await jobsService.requestBundle(runId));
      await waitForZip(runId);
    });

  const copyCommand = async (command: string) => {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const folder = info?.folder;
  const canMakeLink =
    folder && ['none', 'failed', 'expired'].includes(info?.status ?? '');

  return (
    <div className="relative">
      {(message || folder) && (
        <div className={PANEL}>
          {message && <p>{message}</p>}
          {folder && (
            <>
              <p>
                The files stayed on the machine that ran them, in{' '}
                <code className="font-mono break-all">{folder.path}</code>
              </p>
              {folder.copy_command && (
                <div className="flex items-start gap-2">
                  <code className={COMMAND}>
                    {folder.copy_command}
                  </code>
                  <button
                    type="button"
                    title="Copy command"
                    onClick={() => copyCommand(folder.copy_command ?? '')}
                    className="p-1.5 rounded hover:bg-slate-100 cursor-pointer"
                  >
                    {copied ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="w-3.5 h-3.5 text-slate-500" />
                    )}
                  </button>
                </div>
              )}
              {canMakeLink && (
                <button
                  type="button"
                  onClick={makeLink}
                  disabled={busy}
                  className={BUTTON}
                >
                  Make a download link (up to 1 GB)
                </button>
              )}
            </>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={fetchFiles}
        disabled={busy}
        title="Download the whole run, or see where its files are"
        className={BUTTON}
      >
        {busy ? (
          <span className={SPINNER} />
        ) : (
          <Download className="w-3.5 h-3.5 text-orange-500" />
        )}
        <span>Get files</span>
      </button>
    </div>
  );
}

/**
 * Explain a zip that cannot be downloaded right now.
 */
function describe(info: BundleInfo): string {
  if (info.status === 'too_big') {
    const size = ((info.size_bytes ?? 0) / GIGABYTE).toFixed(1);
    return `Too big to download from here (over ${size} GB).`;
  }
  if (info.status === 'failed') {
    return `The zip could not be made: ${info.error ?? 'unknown error'}`;
  }
  if (info.status === 'expired') return 'The last zip has expired.';
  return '';
}
