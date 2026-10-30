import type { ParameterSpec } from '../../types/api';

type FieldKind = 'boolean' | 'number' | 'choice' | 'text';

export const FIELD_NAME = 'text-[13px] text-stone-600';
const FIELD = [
  'h-10 w-full px-3 rounded-[10px] border border-stone-200 bg-white',
  'font-mono text-[13px] text-stone-900 placeholder:text-stone-400',
  'focus:outline-none focus:border-orange-700',
  'disabled:bg-stone-50 disabled:text-stone-500',
].join(' ');
const CHECKBOX = 'w-4 h-4 accent-orange-700 cursor-pointer';

/**
 * Choose the input for one parameter: from the catalog, or guessed
 * from its value when the catalog does not know it.
 */
function fieldKind(spec: ParameterSpec | undefined, value: unknown): FieldKind {
  if (spec?.choices) return 'choice';
  if (spec) {
    if (spec.kind === 'boolean') return 'boolean';
    if (spec.kind === 'integer' || spec.kind === 'number') return 'number';
    return 'text';
  }
  if (typeof value === 'boolean') return 'boolean';
  return typeof value === 'number' ? 'number' : 'text';
}

/**
 * Convert what the person typed or picked into the parameter's type.
 * An emptied optional field becomes null: "use the script's default".
 */
function coerceValue(
  raw: string,
  kind: FieldKind,
  spec: ParameterSpec | undefined
): unknown {
  if (raw === '' && !spec?.required) return null;
  if (kind === 'boolean') return raw === 'true';
  const numeric = spec?.kind === 'integer' || spec?.kind === 'number';
  if (kind === 'number' || (kind === 'choice' && numeric)) {
    const parsed = Number(raw);
    return Number.isNaN(parsed) ? raw : parsed;
  }
  return raw;
}

/**
 * A parameter's name as shown: the catalog's label if it has one,
 * else its own name, with its unit.
 */
function shownName(name: string, spec: ParameterSpec | undefined): string {
  const shown = spec?.label ?? name.replaceAll('_', ' ');
  return spec?.unit ? `${shown} (${spec.unit})` : shown;
}

function Field({
  name,
  value,
  spec,
  locked,
  onChange,
}: {
  name: string;
  value: unknown;
  spec: ParameterSpec | undefined;
  locked: boolean;
  onChange: (value: unknown) => void;
}) {
  const kind = fieldKind(spec, value);
  const id = `parameter-${name}`;
  const help = spec?.help ?? undefined;
  const shown = String(value ?? '');
  const change = (raw: string) => onChange(coerceValue(raw, kind, spec));

  if (kind === 'boolean') {
    return (
      <label className="flex items-center justify-between gap-3" title={help}>
        <span className={FIELD_NAME}>{shownName(name, spec)}</span>
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={locked}
          onChange={(event) => change(String(event.target.checked))}
          className={CHECKBOX}
        />
      </label>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={FIELD_NAME} title={help}>
        {shownName(name, spec)}
      </label>
      {kind === 'choice' ? (
        <select
          id={id}
          value={shown}
          disabled={locked}
          onChange={(event) => change(event.target.value)}
          className={FIELD}
        >
          {!spec?.required && <option value="">(default)</option>}
          {(spec?.choices ?? []).map((choice) => (
            <option key={String(choice)} value={String(choice)}>
              {String(choice)}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={kind === 'number' ? 'number' : 'text'}
          step="any"
          value={shown}
          placeholder={spec && !spec.required ? 'default' : ''}
          disabled={locked}
          onChange={(event) => change(event.target.value)}
          className={FIELD}
        />
      )}
    </div>
  );
}

/**
 * A step's parameters as a form, one field each; the catalog says
 * what kind of field, and its help shows on hover.
 */
export default function ParameterForm({
  parameters,
  specs,
  locked,
  onChange,
}: {
  parameters: Record<string, unknown>;
  specs?: ParameterSpec[];
  locked: boolean;
  onChange: (parameters: Record<string, unknown>) => void;
}) {
  const specByName = new Map((specs ?? []).map((spec) => [spec.name, spec]));
  const names = Object.keys(parameters);
  if (names.length === 0) {
    return <p className="text-[13px] text-stone-500">No parameters.</p>;
  }
  return (
    <div className="flex flex-col gap-3.5">
      {names.map((name) => (
        <Field
          key={name}
          name={name}
          value={parameters[name]}
          spec={specByName.get(name)}
          locked={locked}
          onChange={(value) => onChange({ ...parameters, [name]: value })}
        />
      ))}
    </div>
  );
}
