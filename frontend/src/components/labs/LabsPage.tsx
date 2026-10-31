import { useEffect, useState, type FormEvent } from 'react';
import { describeError } from '../../api/client';
import { labsService } from '../../api/services';
import type { LabSummary } from '../../types/api';
import {
  CARD,
  CARD_FACTS,
  CARD_GRID,
  CARD_TITLE,
  NEW_CARD,
  NEW_CARD_PLUS,
  NEW_CARD_SIGN,
  NEW_CARD_TITLE,
  PAGE,
  PAGE_TITLE,
  PAGE_WIDTH,
} from '../dashboard/cardStyle';

const FORM_CARD = [
  'flex flex-col gap-2 min-h-[160px] p-4 bg-white rounded-xl',
  'border-2 border-dashed border-orange-300',
].join(' ');
const INPUT = [
  'h-9 px-3 rounded-lg border border-slate-300 text-sm',
  'focus:outline-none focus:border-orange-600',
].join(' ');
const CREATE = [
  'h-9 px-4 rounded-lg bg-orange-600 hover:bg-orange-500 text-white',
  'text-sm font-semibold disabled:opacity-50 cursor-pointer',
].join(' ');
const CANCEL = [
  'h-9 px-3 rounded-lg text-sm text-slate-600 hover:bg-slate-100',
  'cursor-pointer',
].join(' ');

function peopleCount(count: number): string {
  return `${count} ${count === 1 ? 'person' : 'people'}`;
}

/**
 * A new lab: its name, and who will run it. Then on to its page.
 */
function NewLabForm({ onCancel }: { onCancel: () => void }) {
  const [name, setName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const lab = await labsService.create(name.trim(), adminEmail.trim());
      window.location.hash = `#lab/${lab.id}`;
    } catch (err) {
      setError(describeError(err, 'Could not make the lab.'));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={create} className={FORM_CARD}>
      <input
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Lab name"
        aria-label="Lab name"
        maxLength={100}
        className={INPUT}
      />
      <input
        value={adminEmail}
        onChange={(event) => setAdminEmail(event.target.value)}
        placeholder="Admin's email"
        aria-label="Admin's email"
        autoComplete="off"
        className={INPUT}
      />
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
      <div className="mt-auto flex gap-2">
        <button
          type="submit"
          disabled={busy || !name.trim() || !adminEmail.trim()}
          className={CREATE}
        >
          Create
        </button>
        <button type="button" onClick={onCancel} className={CANCEL}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function LabCard({ lab }: { lab: LabSummary }) {
  const titles = lab.workflows.map((workflow) => workflow.title).join(', ');
  return (
    <div className="group relative">
      <a href={`#lab/${lab.id}`} className={CARD}>
        <h3 className={CARD_TITLE}>{lab.name}</h3>
        <p className="mb-4 text-sm text-slate-600 line-clamp-2">
          {titles || 'No workflows yet'}
        </p>
        <p className={CARD_FACTS}>{peopleCount(lab.people)}</p>
      </a>
    </div>
  );
}

/**
 * The owner's labs, as cards like the sessions page's.
 */
export default function LabsPage() {
  const [labs, setLabs] = useState<LabSummary[]>([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    labsService
      .list()
      .then((loaded) => current && setLabs(loaded))
      .catch((err) => {
        if (current) setError(describeError(err, 'Could not load the labs.'));
      });
    return () => {
      current = false;
    };
  }, []);

  return (
    <div className={PAGE}>
      <div className={PAGE_WIDTH}>
        <h1 className={`${PAGE_TITLE} mb-8`}>Labs</h1>
        {error && (
          <p role="alert" className="mb-4 text-sm text-red-600">
            {error}
          </p>
        )}
        <div className={CARD_GRID}>
          {adding ? (
            <NewLabForm onCancel={() => setAdding(false)} />
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className={NEW_CARD}
            >
              <div className={NEW_CARD_PLUS}>
                <span className={NEW_CARD_SIGN}>+</span>
              </div>
              <h3 className={NEW_CARD_TITLE}>New lab</h3>
            </button>
          )}
          {labs.map((lab) => (
            <LabCard key={lab.id} lab={lab} />
          ))}
        </div>
      </div>
    </div>
  );
}
