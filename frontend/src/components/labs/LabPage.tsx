import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, X } from 'lucide-react';
import { describeError } from '../../api/client';
import { labsService } from '../../api/services';
import type { PersonChange } from '../../api/services/labsService';
import { useSignedInAccount } from '../../hooks/useAccount';
import type { LabDetail, LabPerson, WorkflowName } from '../../types/api';
import {
  ON_HOVER,
  PAGE,
  PAGE_TITLE,
  PAGE_WIDTH,
} from '../dashboard/cardStyle';
import EditableTitle from '../EditableTitle';

const SECTION = 'mt-8 bg-white rounded-xl border border-slate-200 p-5';
const HEADING = 'text-sm font-semibold text-slate-800';
const TICK = 'w-4 h-4 accent-orange-600 cursor-pointer disabled:cursor-default';
const BACK = [
  'inline-flex items-center gap-1.5 mb-4 text-[13px] font-medium',
  'text-slate-500 hover:text-slate-800',
].join(' ');
const TITLE_INPUT = [
  'h-10 w-96 max-w-full px-2 rounded-md border border-slate-300',
  'text-2xl font-extrabold text-slate-800 focus:outline-none',
  'focus:border-orange-600',
].join(' ');
const TITLE_BUTTON = `${PAGE_TITLE} text-left cursor-text`;
const ADD_INPUT = [
  'h-9 w-72 max-w-full px-3 rounded-lg border border-slate-300 text-sm',
  'focus:outline-none focus:border-orange-600',
].join(' ');
const ADD_BUTTON = [
  'h-9 px-4 rounded-lg bg-orange-600 hover:bg-orange-500 text-white',
  'text-sm font-semibold disabled:opacity-50 cursor-pointer',
].join(' ');
const PEOPLE_BAR = 'flex flex-wrap items-center justify-between gap-3';
const COLUMN = 'py-2 pr-6 text-left text-xs font-medium text-slate-500';
const CELL = 'py-2.5 pr-6 align-middle';
const ROLE_SELECT = [
  'h-7 px-1 rounded border border-slate-200 bg-white text-[13px]',
  'text-slate-700 cursor-pointer',
].join(' ');
const REMOVE = [
  'p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50',
  'transition-all cursor-pointer',
  ON_HOVER,
].join(' ');
const ROLE_NAME = { owner: 'Owner', admin: 'Admin', user: 'User' };

/**
 * Emails as typed: separated by commas, semicolons or spaces.
 */
function emailsIn(text: string): string[] {
  return text.split(/[\s,;]+/).filter(Boolean);
}

/**
 * A list with one item added or taken out.
 */
function toggled(items: string[], item: string, on: boolean): string[] {
  const others = items.filter((name) => name !== item);
  return on ? [...others, item] : others;
}

/**
 * What the lab has: the owner ticks it, its admin only reads it.
 */
function LabWorkflows({
  lab,
  canChange,
  busy,
  onChange,
}: {
  lab: LabDetail;
  canChange: boolean;
  busy: boolean;
  onChange: (workflows: string[]) => void;
}) {
  const has = lab.workflows.map((workflow) => workflow.id);
  if (!canChange) {
    const titles = lab.workflows.map((workflow) => workflow.title);
    return (
      <p className="mt-2 text-sm text-slate-700">
        {titles.join(', ') || 'No workflows yet.'}
      </p>
    );
  }
  return (
    <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
      {lab.available.map((workflow) => (
        <label
          key={workflow.id}
          className="flex items-center gap-2 text-sm text-slate-700"
        >
          <input
            type="checkbox"
            checked={has.includes(workflow.id)}
            disabled={busy}
            onChange={(event) =>
              onChange(toggled(has, workflow.id, event.target.checked))
            }
            className={TICK}
          />
          {workflow.title}
        </label>
      ))}
    </div>
  );
}

function PersonName({ person }: { person: LabPerson }) {
  return (
    <>
      <div className="text-slate-800">{person.name || person.email}</div>
      {person.name && (
        <div className="text-xs text-slate-500">{person.email}</div>
      )}
      {!person.last_seen_at && (
        <div className="text-xs text-slate-400">Not signed in yet</div>
      )}
    </>
  );
}

function PersonRow({
  person,
  workflows,
  isOwner,
  busy,
  onChange,
  onRemove,
}: {
  person: LabPerson;
  workflows: WorkflowName[];
  isOwner: boolean;
  busy: boolean;
  onChange: (change: PersonChange) => void;
  onRemove: () => void;
}) {
  const isAdmin = person.role === 'admin';
  const who = person.name || person.email;
  return (
    <tr className="group border-t border-slate-100">
      <td className={CELL}>
        <PersonName person={person} />
      </td>
      <td className={CELL}>
        {isOwner ? (
          <select
            value={person.role}
            disabled={busy}
            aria-label={`Role of ${who}`}
            onChange={(event) =>
              onChange({ role: event.target.value as PersonChange['role'] })
            }
            className={ROLE_SELECT}
          >
            <option value="admin">{ROLE_NAME.admin}</option>
            <option value="user">{ROLE_NAME.user}</option>
          </select>
        ) : (
          <span className="text-[13px] text-slate-600">
            {ROLE_NAME[person.role]}
          </span>
        )}
      </td>
      {workflows.map((workflow) => (
        <td key={workflow.id} className={CELL}>
          {isAdmin ? (
            <span className="text-xs text-slate-400">Always on</span>
          ) : (
            <input
              type="checkbox"
              checked={person.workflows.includes(workflow.id)}
              disabled={busy}
              aria-label={`${workflow.title} for ${who}`}
              onChange={(event) =>
                onChange({
                  workflows: toggled(
                    person.workflows,
                    workflow.id,
                    event.target.checked
                  ),
                })
              }
              className={TICK}
            />
          )}
        </td>
      ))}
      <td className="py-2.5 text-right align-middle">
        {(isOwner || !isAdmin) && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${who}`}
            className={REMOVE}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </td>
    </tr>
  );
}

function AddPeople({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (emails: string[]) => Promise<boolean>;
}) {
  const [text, setText] = useState('');
  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (await onAdd(emailsIn(text))) setText('');
  };
  return (
    <form onSubmit={add} className="flex flex-wrap items-center gap-2">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Emails, comma separated"
        aria-label="Emails to add"
        autoComplete="off"
        className={ADD_INPUT}
      />
      <button
        type="submit"
        disabled={busy || emailsIn(text).length === 0}
        className={ADD_BUTTON}
      >
        Add
      </button>
    </form>
  );
}

/**
 * One lab: the workflows it has, and its people with what is ticked
 * for each. The owner changes everything; its admin ticks and adds.
 */
export default function LabPage({ labId }: { labId: string }) {
  const account = useSignedInAccount();
  const isOwner = account.role === 'owner';
  const [lab, setLab] = useState<LabDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    labsService
      .get(labId)
      .then((loaded) => current && setLab(loaded))
      .catch((err) => {
        if (current) setError(describeError(err, 'Could not load the lab.'));
      });
    return () => {
      current = false;
    };
  }, [labId]);

  // Every change answers with the lab as it now stands.
  const change = useCallback(
    async (request: () => Promise<LabDetail>): Promise<boolean> => {
      setBusy(true);
      setError(null);
      try {
        setLab(await request());
        return true;
      } catch (err) {
        setError(describeError(err, 'That did not work.'));
        return false;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const remove = (person: LabPerson) => {
    const who = person.name || person.email;
    const asked = `Remove ${who} from this lab? They are signed out at once.`;
    if (!confirm(asked)) return;
    void change(() => labsService.removePerson(labId, person.id));
  };

  return (
    <div className={PAGE}>
      <div className={PAGE_WIDTH}>
        {isOwner && (
          <a href="#labs" className={BACK}>
            <ArrowLeft size={16} />
            Labs
          </a>
        )}
        {lab &&
          (isOwner ? (
            <div>
              <EditableTitle
                title={lab.name}
                onRename={(name) => {
                  if (!name.trim()) return;
                  void change(() => labsService.change(labId, { name }));
                }}
                className={TITLE_BUTTON}
                inputClassName={TITLE_INPUT}
                label="Lab name"
              />
            </div>
          ) : (
            <h1 className={PAGE_TITLE}>{lab.name}</h1>
          ))}
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {error}
          </p>
        )}
        {lab && (
          <>
            <section className={SECTION}>
              <h2 className={HEADING}>Workflows</h2>
              <LabWorkflows
                lab={lab}
                canChange={isOwner}
                busy={busy}
                onChange={(workflows) =>
                  void change(() => labsService.change(labId, { workflows }))
                }
              />
            </section>
            <section className={SECTION}>
              <div className={PEOPLE_BAR}>
                <h2 className={HEADING}>People</h2>
                <AddPeople
                  busy={busy}
                  onAdd={(emails) =>
                    change(() => labsService.addPeople(labId, emails))
                  }
                />
              </div>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className={COLUMN}>Person</th>
                      <th className={COLUMN}>Role</th>
                      {lab.workflows.map((workflow) => (
                        <th key={workflow.id} className={COLUMN}>
                          {workflow.title}
                        </th>
                      ))}
                      <th aria-label="Remove" />
                    </tr>
                  </thead>
                  <tbody>
                    {lab.people.map((person) => (
                      <PersonRow
                        key={person.id}
                        person={person}
                        workflows={lab.workflows}
                        isOwner={isOwner}
                        busy={busy}
                        onChange={(personChange) =>
                          void change(() =>
                            labsService.changePerson(
                              labId,
                              person.id,
                              personChange
                            )
                          )
                        }
                        onRemove={() => remove(person)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
