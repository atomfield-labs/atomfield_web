import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Check, Copy } from 'lucide-react';
import { describeError } from '../../api/client';
import { authService } from '../../api/services/authService';
import { useSignedInAccount } from '../../hooks/useAccount';
import type {
  NewScriptKey,
  ScriptKey,
  UserStatsResponse,
} from '../../types/api';

const COPIED_MS = 2000;
const REVOKE_QUESTION = 'Revoke this key? Scripts using it stop working.';

const PRIMARY_BUTTON = [
  'h-9 px-4 rounded-lg bg-orange-700 hover:bg-orange-800 text-white',
  'text-sm font-semibold disabled:opacity-50 cursor-pointer',
].join(' ');
const INPUT = [
  'h-9 flex-1 min-w-0 px-3 rounded-lg border border-stone-300 text-sm',
  'focus:outline-none focus:border-orange-600',
].join(' ');
const SECTION_TITLE = 'text-sm font-semibold text-stone-900';

/**
 * A date the way the person reads dates.
 */
function shortDate(iso?: string | null): string {
  return iso ? new Date(iso).toLocaleDateString() : '';
}

function Quota({ stats }: { stats: UserStatsResponse }) {
  const left = Math.max(0, stats.quota_remaining);
  const share = stats.quota_limit ? left / stats.quota_limit : 0;
  const running = stats.running_jobs + stats.pending_jobs;
  return (
    <section className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className={SECTION_TITLE}>Jobs left</span>
        <span className="text-stone-600">
          {left} of {stats.quota_limit}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-orange-600"
          style={{ width: `${Math.round(share * 100)}%` }}
        />
      </div>
      <p className="text-[13px] text-stone-500">
        {stats.total_jobs} jobs · {stats.success_jobs} finished ·{' '}
        {stats.failed_jobs} failed · {running} running
      </p>
    </section>
  );
}

function NewKeyBox({ made }: { made: NewScriptKey }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(made.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), COPIED_MS);
  };
  return (
    <div className="space-y-2 rounded-lg border border-orange-200 p-3">
      <p className="text-[13px] text-stone-600">
        Copy it now. It won't be shown again.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all font-mono text-xs select-all">
          {made.api_key}
        </code>
        <button
          type="button"
          onClick={copy}
          title="Copy"
          className="p-2 rounded-md hover:bg-stone-100 cursor-pointer"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </div>
    </div>
  );
}

function KeyRow({
  scriptKey,
  onRevoke,
}: {
  scriptKey: ScriptKey;
  onRevoke: (key: ScriptKey) => void;
}) {
  const used = scriptKey.last_used_at
    ? `Last used ${shortDate(scriptKey.last_used_at)}`
    : 'Never used';
  return (
    <li className="flex items-center gap-3 py-2.5 text-sm">
      <span className="flex-1 min-w-0 truncate">
        {scriptKey.label || 'Key'}
      </span>
      <code className="font-mono text-xs text-stone-500">
        {scriptKey.key_prefix}
      </code>
      <span className="w-32 text-[13px] text-stone-500">{used}</span>
      <button
        type="button"
        onClick={() => onRevoke(scriptKey)}
        className="text-[13px] text-red-700 hover:underline cursor-pointer"
      >
        Revoke
      </button>
    </li>
  );
}

interface KeyList {
  keys: ScriptKey[];
  error: string | null;
}

/**
 * The person's keys, or why they could not be read.
 */
async function readKeys(): Promise<KeyList> {
  try {
    return { keys: await authService.listKeys(), error: null };
  } catch (err) {
    const error = describeError(err, 'Could not load your keys.');
    return { keys: [], error };
  }
}

function ScriptKeys() {
  const [keys, setKeys] = useState<ScriptKey[]>([]);
  const [label, setLabel] = useState('');
  const [made, setMade] = useState<NewScriptKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showKeys = useCallback((found: KeyList) => {
    setKeys(found.keys);
    setError(found.error);
  }, []);

  useEffect(() => {
    void readKeys().then((found) => showKeys(found));
  }, [showKeys]);

  const reload = async () => showKeys(await readKeys());

  const makeKey = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setMade(await authService.makeKey(label.trim()));
      setLabel('');
      await reload();
    } catch (err) {
      setError(describeError(err, 'Could not make a key.'));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (key: ScriptKey) => {
    if (!window.confirm(REVOKE_QUESTION)) return;
    try {
      await authService.revokeKey(key.id);
      if (made?.id === key.id) setMade(null);
      await reload();
    } catch (err) {
      setError(describeError(err, 'Could not revoke the key.'));
    }
  };

  return (
    <section className="space-y-3">
      <h2 className={SECTION_TITLE}>Keys for scripts</h2>
      <form onSubmit={makeKey} className="flex gap-2">
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="What is it for?"
          maxLength={100}
          className={INPUT}
        />
        <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
          Make key
        </button>
      </form>
      {made && <NewKeyBox made={made} />}
      {error && (
        <p role="alert" className="text-[13px] text-red-700">
          {error}
        </p>
      )}
      {keys.length > 0 && (
        <ul className="divide-y divide-stone-100">
          {keys.map((key) => (
            <KeyRow key={key.id} scriptKey={key} onRevoke={revoke} />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Who you are, how many jobs you have left, and your keys for scripts.
 */
export default function AccountPage() {
  const account = useSignedInAccount();
  const [stats, setStats] = useState<UserStatsResponse | null>(null);

  useEffect(() => {
    let current = true;
    void authService.getStats().then((loaded) => {
      if (current) setStats(loaded);
    });
    return () => {
      current = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-white px-6 pt-28 pb-16">
      <div className="mx-auto max-w-xl space-y-10">
        <header>
          <h1 className="text-2xl font-semibold text-stone-900">
            {account.label || account.email}
          </h1>
          {account.label && (
            <p className="text-sm text-stone-500">{account.email}</p>
          )}
        </header>
        {stats && <Quota stats={stats} />}
        <ScriptKeys />
      </div>
    </div>
  );
}
