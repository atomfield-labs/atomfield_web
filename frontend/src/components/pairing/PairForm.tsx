import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { describeError, statusOf } from '../../api/client';
import { pairingService } from '../../api/services';
import type { ComputeTarget, PairingView } from '../../types/api';

const NOT_FOUND = 404;
const NOT_WAITING =
  'No computer is waiting with this code. Codes last 10 minutes.';

const BUTTON = [
  'h-9 px-4 rounded-lg bg-orange-600 hover:bg-orange-500 text-white',
  'text-sm font-semibold disabled:opacity-50 cursor-pointer',
].join(' ');
const QUIET_BUTTON = [
  'h-9 px-4 rounded-lg text-sm text-stone-600 hover:bg-stone-100',
  'cursor-pointer',
].join(' ');
const INPUT = [
  'h-9 flex-1 min-w-0 px-3 rounded-lg border border-stone-300 text-sm',
  'focus:outline-none focus:border-orange-600',
].join(' ');
const LABEL = 'block text-sm font-medium text-stone-700';

type Step =
  | { name: 'enter' }
  | { name: 'review'; pairing: PairingView }
  | { name: 'done'; target: ComputeTarget };

/**
 * Look a code up: the computer waiting with it, or what to tell the
 * person.
 */
async function lookUp(code: string): Promise<Step | string> {
  try {
    return { name: 'review', pairing: await pairingService.see(code) };
  } catch (error) {
    if (statusOf(error) === NOT_FOUND) return NOT_WAITING;
    return describeError(error, 'Could not look the code up.');
  }
}

function CodeStep({
  code,
  busy,
  onCode,
  onNext,
}: {
  code: string;
  busy: boolean;
  onCode: (code: string) => void;
  onNext: (event: FormEvent) => void;
}) {
  return (
    <form onSubmit={onNext} className="space-y-2">
      <label htmlFor="pair-code" className={LABEL}>
        Code shown by the agent
      </label>
      <div className="flex gap-2">
        <input
          id="pair-code"
          value={code}
          onChange={(event) => onCode(event.target.value.toUpperCase())}
          placeholder="QKTW-MZRB"
          autoComplete="off"
          spellCheck={false}
          maxLength={12}
          className={`${INPUT} font-mono tracking-wider`}
        />
        <button
          type="submit"
          disabled={busy || !code.trim()}
          className={BUTTON}
        >
          Next
        </button>
      </div>
    </form>
  );
}

function ReviewStep({
  pairing,
  busy,
  onConnect,
  onCancel,
}: {
  pairing: PairingView;
  busy: boolean;
  onConnect: (name: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(pairing.hostname);
  const asked = new Date(pairing.requested_at).toLocaleTimeString();
  const connect = (event: FormEvent) => {
    event.preventDefault();
    onConnect(name.trim());
  };
  return (
    <form onSubmit={connect} className="space-y-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-stone-500">Computer</dt>
        <dd>{pairing.hostname}</dd>
        <dt className="text-stone-500">User</dt>
        <dd>{pairing.username}</dd>
        <dt className="text-stone-500">From</dt>
        <dd>{pairing.address}</dd>
        <dt className="text-stone-500">Asked at</dt>
        <dd>{asked}</dd>
      </dl>
      <p className="text-[13px] text-stone-500">
        Connect it only if you just ran login there.
      </p>
      <div className="space-y-2">
        <label htmlFor="pair-name" className={LABEL}>
          Name
        </label>
        <input
          id="pair-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={100}
          className={`${INPUT} w-full`}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className={BUTTON}
        >
          Connect
        </button>
        <button type="button" onClick={onCancel} className={QUIET_BUTTON}>
          Not mine
        </button>
      </div>
    </form>
  );
}

/**
 * Pair a computer's agent: enter the code it shows (or arrive with it
 * in the link), check which computer is asking, name it, connect.
 */
export default function PairForm({
  initialCode = '',
  onDone,
}: {
  initialCode?: string;
  onDone?: (target: ComputeTarget) => void;
}) {
  const [code, setCode] = useState(initialCode);
  const [step, setStep] = useState<Step>({ name: 'enter' });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const show = useCallback((found: Step | string) => {
    if (typeof found === 'string') {
      setError(found);
      return;
    }
    setError(null);
    setStep(found);
  }, []);

  // Arriving by the agent's link: look its code up at once.
  useEffect(() => {
    if (!initialCode) return;
    void lookUp(initialCode).then((found) => show(found));
  }, [initialCode, show]);

  const next = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    show(await lookUp(code));
    setBusy(false);
  };

  const connect = async (pairing: PairingView, name: string) => {
    setBusy(true);
    try {
      const target = await pairingService.approve(pairing.code, name);
      show({ name: 'done', target });
      onDone?.(target);
    } catch (err) {
      const lost = statusOf(err) === NOT_FOUND;
      setError(lost ? NOT_WAITING : describeError(err, 'Could not connect.'));
    } finally {
      setBusy(false);
    }
  };

  const restart = () => {
    setCode('');
    setError(null);
    setStep({ name: 'enter' });
  };

  return (
    <div className="space-y-3">
      {step.name === 'enter' && (
        <CodeStep code={code} busy={busy} onCode={setCode} onNext={next} />
      )}
      {step.name === 'review' && (
        <ReviewStep
          pairing={step.pairing}
          busy={busy}
          onConnect={(name) => void connect(step.pairing, name)}
          onCancel={restart}
        />
      )}
      {step.name === 'done' && (
        <p className="text-sm text-stone-700">
          <strong>{step.target.name}</strong> is connected. Start its agent
          there; it shows as online once it runs.
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
