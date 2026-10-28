import { useState } from 'react';
import { Check, Copy, X } from 'lucide-react';
import { targetsService } from '../../api/services';
import type { TargetToken } from '../../types/api';

interface AddClusterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (created: TargetToken) => void;
}

const OVERLAY = [
  'fixed inset-0 z-50 flex items-center justify-center p-4',
  'bg-slate-950/60',
].join(' ');
const CARD = [
  'w-full max-w-lg bg-white rounded-xl shadow-xl border border-slate-200',
  'p-5 space-y-4 text-sm text-slate-700',
].join(' ');
const CODE = [
  'flex-1 p-2 bg-slate-50 rounded font-mono text-xs break-all',
  'border border-slate-200',
].join(' ');
const BUTTON = [
  'px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50',
  'text-white text-sm font-bold rounded-lg',
].join(' ');

/**
 * A line of text with a copy button.
 */
function Copyable({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="flex items-start gap-2">
      <code className={CODE}>{text}</code>
      <button
        type="button"
        title="Copy"
        onClick={copy}
        className="p-1.5 rounded hover:bg-slate-100 cursor-pointer"
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-emerald-600" />
        ) : (
          <Copy className="w-3.5 h-3.5 text-slate-500" />
        )}
      </button>
    </div>
  );
}

/**
 * Add a cluster: name it, then copy its agent token (shown only now)
 * and the two commands to run on the cluster's login node.
 */
export default function AddClusterModal({
  isOpen,
  onClose,
  onCreated,
}: AddClusterModalProps) {
  const [name, setName] = useState('');
  const [created, setCreated] = useState<TargetToken | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const close = () => {
    setName('');
    setCreated(null);
    setError(null);
    onClose();
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await targetsService.create(name.trim(), 'slurm');
      setCreated(result);
      onCreated(result);
    } catch {
      setError('Could not add the cluster. Are you signed in?');
    } finally {
      setBusy(false);
    }
  };

  const login = created
    ? 'python -m agent login --api-url <public address of this server>' +
      ` --token ${created.token}`
    : '';

  return (
    <div className={OVERLAY}>
      <div className={CARD}>
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900">Add a cluster</h2>
          <button type="button" onClick={close} title="Close">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        {!created ? (
          <>
            <p>
              Give it a name you will recognise, such as the cluster's
              name. Its agent will run your jobs there through Slurm.
            </p>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. my-cluster"
              maxLength={100}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg"
            />
            {error && <p className="text-red-600">{error}</p>}
            <button
              type="button"
              onClick={create}
              disabled={busy || !name.trim()}
              className={BUTTON}
            >
              Add cluster
            </button>
          </>
        ) : (
          <>
            <p>
              <strong>{created.target.name}</strong> is added. Copy its
              agent token now: it is shown only once (you can make a new
              one later).
            </p>
            <Copyable text={created.token} />
            <p>
              On the cluster's login node, in the AtomField code folder,
              run:
            </p>
            <Copyable text={login} />
            <Copyable text="python -m agent start" />
            <p className="text-xs text-slate-500">
              The cluster shows as online in "Run on" once its agent
              calls in.
            </p>
            <button type="button" onClick={close} className={BUTTON}>
              Done
            </button>
          </>
        )}
      </div>
    </div>
  );
}
