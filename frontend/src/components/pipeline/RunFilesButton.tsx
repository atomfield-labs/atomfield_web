import { useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';
import { jobsService } from '../../api/services';
import type { BundleInfo } from '../../types/api';

// A zip on its way: keep asking until it is ready (about 2 minutes).
const WAITING = new Set(['requested', 'packing']);
const POLL_MS = 2000;
const MAX_POLLS = 60;
const GIGABYTE = 1024 ** 3;
const COMMAND = 'flex-1 p-2 bg-stone-50 rounded font-mono break-all';
const SPINNER = [
  'w-3.5 h-3.5 border-2 border-stone-400 border-t-transparent',
  'rounded-full animate-spin',
].join(' ');

const BUTTON = [
  'h-9 px-3 flex items-center gap-2 rounded-[10px] border border-stone-200',
  'bg-white hover:bg-stone-50 text-sm text-stone-800 cursor-pointer',
  'disabled:opacity-50',
].join(' ');
const NOTE = [
  'p-3 rounded-[10px] border border-stone-200 text-xs text-stone-700',
  'space-y-2',
].join(' ');

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
      // The server's own store gives a path on this site, a cloud
      // store a full URL; the browser opens either.
      window.location.assign(current.download_url);
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
    <div className="flex flex-col items-start gap-2">
      {(message || folder) && (
        <div className={NOTE}>
          {message && <p>{message}</p>}
          {folder && (
            <>
              <p>
                The files stayed on the machine that ran them, in{' '}
                <code className="font-mono break-all">{folder.path}</code>
              </p>
              {info?.made_with && (
                <p className="text-stone-500">
                  Made with{' '}
                  <code className="font-mono">
                    {[info.made_with, ...(info.data_packs ?? [])].join(' · ')}
                  </code>
                </p>
              )}
              {folder.copy_command && (
                <div className="flex items-start gap-2">
                  <code className={COMMAND}>
                    {folder.copy_command}
                  </code>
                  <button
                    type="button"
                    title="Copy command"
                    onClick={() => copyCommand(folder.copy_command ?? '')}
                    className="p-1.5 rounded hover:bg-stone-100 cursor-pointer"
                  >
                    {copied ? (
                      <Check className="w-3.5 h-3.5 text-green-600" />
                    ) : (
                      <Copy className="w-3.5 h-3.5 text-stone-500" />
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
          <Download className="w-3.5 h-3.5 text-stone-500" />
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
    const size = formatSize(info.size_bytes ?? 0);
    return `Too big to download from here (${size}); copy the folder instead.`;
  }
  if (info.status === 'failed') {
    return `The zip could not be made: ${info.error ?? 'unknown error'}`;
  }
  if (info.status === 'expired') return 'The last zip has expired.';
  return '';
}

/**
 * A size people can read: MB below a gigabyte, GB above.
 */
function formatSize(bytes: number): string {
  if (bytes < GIGABYTE) return `${Math.round(bytes / (1024 * 1024))} MB`;
  return `${(bytes / GIGABYTE).toFixed(1)} GB`;
}
