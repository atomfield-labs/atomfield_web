import { useMemo } from 'react';
import type { ParameterSpec } from '../../types/api';

interface YamlParamEditorProps {
  parameters: Record<string, any>;
  onChange: (newParams: Record<string, any>) => void;
  // From the task catalog; without it, types are guessed from values.
  specs?: ParameterSpec[];
}

type EditorKind = 'boolean' | 'number' | 'choice' | 'text';

const VALUE_CLASS = [
  'flex-1 max-w-[240px] text-left font-semibold text-violet-600',
  'bg-transparent border-0 focus:outline-none focus:border-b',
  'focus:border-violet-400 px-0 py-0 text-xs',
].join(' ');

const SELECT_CLASS = [
  'appearance-none bg-transparent font-semibold text-violet-600',
  'hover:text-violet-700 text-xs pr-4 pl-0 py-0 border-0',
  'focus:outline-none focus:border-b focus:border-violet-400',
  'cursor-pointer rounded-none',
].join(' ');

const TOGGLE_CLASS = [
  'font-bold text-violet-600 hover:text-violet-700 hover:underline',
  'select-none transition-colors',
].join(' ');

/**
 * Choose the input control for one parameter.
 */
function editorKind(spec: ParameterSpec | undefined, value: unknown) {
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
 * Convert what the user typed or picked into the parameter's type.
 * An emptied optional field becomes null: "use the script's default".
 */
function coerceValue(
  raw: string,
  kind: EditorKind,
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

export default function YamlParamEditor({
  parameters,
  onChange,
  specs,
}: YamlParamEditorProps) {
  const specByName = useMemo(
    () => new Map((specs ?? []).map((spec) => [spec.name, spec])),
    [specs]
  );
  const keys = useMemo(() => Object.keys(parameters || {}), [parameters]);

  const handleValueChange = (key: string, raw: string, kind: EditorKind) => {
    onChange({
      ...(parameters || {}),
      [key]: coerceValue(raw, kind, specByName.get(key)),
    });
  };

  return (
    <div className="flex flex-col font-mono text-xs">
      <div className="space-y-1">
        {keys.length === 0 ? (
          <div className="py-2 text-slate-400 italic text-xs">
            # no parameters configured
          </div>
        ) : (
          keys.map((key) => {
            const val = parameters[key];
            const spec = specByName.get(key);
            const kind = editorKind(spec, val);
            const shown = val !== undefined && val !== null ? val : '';

            return (
              <div key={key} className="flex items-center py-0.5 group">
                {/* YAML key (orange); hover shows the script's help */}
                <span
                  className="text-orange-600 font-bold select-none shrink-0"
                  title={spec?.help ?? undefined}
                >
                  {key}
                </span>
                <span className="text-slate-400 select-none mr-2">:</span>

                {/* YAML value (violet) */}
                {kind === 'boolean' ? (
                  <button
                    type="button"
                    onClick={() =>
                      handleValueChange(key, String(!val), 'boolean')
                    }
                    className={TOGGLE_CLASS}
                  >
                    {val ? 'true' : 'false'}
                  </button>
                ) : kind === 'choice' ? (
                  <div className="relative inline-flex items-center">
                    <select
                      value={String(shown)}
                      onChange={(e) =>
                        handleValueChange(key, e.target.value, 'choice')
                      }
                      className={SELECT_CLASS}
                    >
                      {!spec?.required && <option value="">(default)</option>}
                      {(spec?.choices ?? []).map((choice) => (
                        <option
                          key={String(choice)}
                          value={String(choice)}
                          className="bg-white text-slate-800 font-mono"
                        >
                          {String(choice)}
                        </option>
                      ))}
                    </select>
                    <span className="pointer-events-none -ml-3 text-[9px]">
                      ▾
                    </span>
                  </div>
                ) : (
                  <input
                    type={kind === 'number' ? 'number' : 'text'}
                    step="any"
                    value={shown}
                    placeholder={spec && !spec.required ? 'default' : ''}
                    onChange={(e) =>
                      handleValueChange(key, e.target.value, kind)
                    }
                    className={VALUE_CLASS}
                  />
                )}
                {spec?.unit && (
                  <span className="ml-1 text-slate-400 select-none">
                    {spec.unit}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
