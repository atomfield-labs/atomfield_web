import { useState } from 'react';
import { Check, Copy, X } from 'lucide-react';
import PairForm from '../pairing/PairForm';
import type { ComputeTarget } from '../../types/api';

interface AddClusterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPaired: (target: ComputeTarget) => void;
}

// Run on the cluster; the copy step installs this shortcut.
const LOGIN_COMMAND = '~/atomfield/agent login';
const SHIP_COMMAND = 'python -m agent.ship <ssh name of the cluster>';
const COPIED_MS = 1500;

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

/**
 * A line of text with a copy button.
 */
function Copyable({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), COPIED_MS);
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
 * Add a cluster: its agent's login shows a code, and entering the
 * code here connects it. No token is copied.
 */
export default function AddClusterModal({
  isOpen,
  onClose,
  onPaired,
}: AddClusterModalProps) {
  if (!isOpen) return null;
  return (
    <div className={OVERLAY}>
      <div className={CARD}>
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900">Add a cluster</h2>
          <button type="button" onClick={onClose} title="Close">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
        <p>On the cluster, run:</p>
        <Copyable text={LOGIN_COMMAND} />
        <p>It shows a code. Enter it here.</p>
        <PairForm onDone={onPaired} />
        <p className="text-xs text-slate-500">
          First time on this cluster? Copy the agent there from your
          AtomField folder:
        </p>
        <Copyable text={SHIP_COMMAND} />
      </div>
    </div>
  );
}
