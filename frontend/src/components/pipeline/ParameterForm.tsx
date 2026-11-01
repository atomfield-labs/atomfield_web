import { useId, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { ParameterSpec, ParameterValue } from '../../types/api';
import {
  ChoiceButtons,
  DoubleSpinBox,
  Dropdown,
  FieldShell,
  FixedValue,
  MeshBox,
  Reveal,
  SpinBox,
  TextBox,
  Toggle,
} from '../widgets';
import type { ChoiceOption } from '../widgets';

type Parameters = Record<string, ParameterValue>;

interface ParameterFormProps {
  parameters: Parameters;
  onChange: (parameters: Parameters) => void;
  // From the task catalog; without it, guessed from the saved values.
  specs?: ParameterSpec[];
}

interface FormCardSpec {
  title: string;
  fields: ParameterSpec[];
}

// Up to this many short choices are buttons; others are a menu.
const MAX_BUTTONS = 4;
const MAX_BUTTON_CHARACTERS = 22;
const DEFAULT_WORD = 'default';
const MESH_SIZE = 3;
const SIDE_BY_SIDE = 2;
const ROW_OF_NUMBERS = 3;
const CARD = [
  'rounded-lg border border-slate-200 bg-white px-3 pt-2.5',
  'transition-colors hover:border-orange-200',
].join(' ');
const CARD_TITLE = [
  'mb-2 text-[10px] font-semibold tracking-wider uppercase',
  'text-slate-400',
].join(' ');
const ADVANCED_BUTTON = [
  'flex items-center gap-1.5 self-start py-0.5 text-xs font-medium',
  'text-slate-500 hover:text-orange-600 transition-colors cursor-pointer',
].join(' ');
const CHANGED_DOT = 'w-1.5 h-1.5 rounded-full bg-orange-500';

/**
 * A description for a value the catalog doesn't know, from its type.
 */
function guessedSpec(name: string, value: ParameterValue): ParameterSpec {
  const kinds: Record<string, ParameterSpec['kind']> = {
    boolean: 'boolean',
    number: 'number',
  };
  return {
    name,
    flag: '',
    kind: kinds[typeof value] ?? 'string',
    default: null,
    choices: null,
    multiple: false,
    required: false,
    help: null,
    label: null,
    unit: null,
    minimum: null,
    maximum: null,
  };
}

/**
 * Every parameter the form shows: the catalog's in its order. A saved
 * value the task no longer takes isn't sent, so it isn't shown either;
 * only a task the catalog doesn't know is guessed from its values.
 */
function allFields(
  parameters: Parameters,
  specs?: ParameterSpec[]
): ParameterSpec[] {
  if (specs) return specs;
  return Object.keys(parameters).map((name) =>
    guessedSpec(name, parameters[name])
  );
}

/**
 * The cards of the form, by each parameter's group, first seen first.
 */
function cardsOf(fields: ParameterSpec[]): FormCardSpec[] {
  const cards = new Map<string, ParameterSpec[]>();
  for (const spec of fields) {
    const title = spec.group ?? '';
    cards.set(title, [...(cards.get(title) ?? []), spec]);
  }
  return [...cards].map(([title, members]) => ({ title, fields: members }));
}

function meshParts(text: ParameterValue): number[] | null {
  const parts = String(text ?? '').trim().split(/\s+/).map(Number);
  const good = parts.length === MESH_SIZE && parts.every(Number.isInteger);
  return good ? parts : null;
}

/**
 * Whether a field takes two columns: three boxes, or text of any length.
 */
function isWide(spec: ParameterSpec): boolean {
  return spec.widget === 'mesh' || (spec.kind === 'string' && !spec.choices);
}

/**
 * How many fields stand side by side in a card of the two column form:
 * three number boxes fit one row, anything else needs the room.
 */
function acrossIn(card: FormCardSpec): 2 | 3 {
  const isNumber = (spec: ParameterSpec) =>
    !spec.choices && (spec.kind === 'integer' || spec.kind === 'number');
  const fits =
    card.fields.length === ROW_OF_NUMBERS && card.fields.every(isNumber);
  return fits ? ROW_OF_NUMBERS : SIDE_BY_SIDE;
}

/**
 * Two columns of cards of about equal height, each card going to the
 * shorter one. Decided from every field, shown or not, so a card never
 * moves across when a field opens.
 */
function intoColumns(cards: FormCardSpec[]): [FormCardSpec[], FormCardSpec[]] {
  const columns: [FormCardSpec[], FormCardSpec[]] = [[], []];
  const heights = [0, 0];
  for (const card of cards) {
    const wide = card.fields.filter(isWide).length;
    const narrow = card.fields.length - wide;
    const rows = wide + Math.ceil(narrow / acrossIn(card));
    const shorter = heights[0] <= heights[1] ? 0 : 1;
    columns[shorter].push(card);
    heights[shorter] += rows + 1;
  }
  return columns;
}

/**
 * The options of a parameter with choices; one with no default of its
 * own can also be left to the script.
 */
function choiceOptions(spec: ParameterSpec): ChoiceOption[] {
  const options = (spec.choices ?? []).map((choice) => ({
    label: String(choice),
    value: choice,
  }));
  if (spec.default !== null || spec.required) return options;
  return [{ label: DEFAULT_WORD, value: null }, ...options];
}

function fitsAsButtons(options: ChoiceOption[]): boolean {
  const characters = options.reduce(
    (sum, option) => sum + option.label.length,
    0
  );
  return (
    options.length <= MAX_BUTTONS && characters <= MAX_BUTTON_CHARACTERS
  );
}

/**
 * The value a parameter stands at: its own, else its default.
 */
function currentValue(
  spec: ParameterSpec,
  parameters: Parameters
): ParameterValue {
  return parameters[spec.name] ?? spec.default ?? null;
}

function isShown(
  spec: ParameterSpec,
  parameters: Parameters,
  fields: ParameterSpec[]
): boolean {
  return Object.entries(spec.show_when ?? {}).every(([name, wanted]) => {
    const other = fields.find((field) => field.name === name);
    return !!other && currentValue(other, parameters) === wanted;
  });
}

function placeholderOf(spec: ParameterSpec): string {
  return spec.default === null ? DEFAULT_WORD : String(spec.default);
}

function numberOf(value: ParameterValue): number | null {
  const number = typeof value === 'string' ? Number(value) : value;
  return typeof number === 'number' && Number.isFinite(number) ? number : null;
}

interface FieldProps {
  spec: ParameterSpec;
  value: ParameterValue;
  isVisible: boolean;
  onChange: (value: ParameterValue) => void;
}

/**
 * One parameter: its label, and the widget its description calls for.
 */
function ParameterField({ spec, value, isVisible, onChange }: FieldProps) {
  const id = useId();
  const [problem, setProblem] = useState<string | null>(null);
  const label = spec.label ?? spec.name;
  const options = choiceOptions(spec);
  const mesh = spec.widget === 'mesh' ? meshParts(value ?? spec.default) : null;
  const numberProps = {
    id,
    label,
    value: numberOf(value),
    onChange,
    onProblem: setProblem,
    minimum: spec.minimum,
    maximum: spec.maximum,
    required: spec.required,
    step: spec.step,
    startFrom: numberOf(spec.default),
    placeholder: placeholderOf(spec),
    unit: spec.unit,
  };

  let widget;
  if (spec.choices && options.length === 1) {
    widget = <FixedValue text={options[0].label} />;
  } else if (spec.choices) {
    const chosen = (value ?? spec.default ?? null) as ChoiceOption['value'];
    const choice = { options, value: chosen };
    widget = fitsAsButtons(options) ? (
      <ChoiceButtons
        label={label}
        onChange={onChange}
        {...choice}
      />
    ) : (
      <Dropdown
        id={id}
        onChange={onChange}
        {...choice}
      />
    );
  } else if (mesh) {
    widget = (
      <MeshBox
        id={id}
        label={label}
        parts={mesh}
        onChange={onChange}
        onProblem={setProblem}
      />
    );
  } else if (spec.kind === 'boolean') {
    widget = (
      <Toggle
        id={id}
        value={value === true}
        onChange={onChange}
      />
    );
  } else if (spec.kind === 'integer') {
    widget = <SpinBox {...numberProps} />;
  } else if (spec.kind === 'number') {
    widget = (
      <DoubleSpinBox
        {...numberProps}
        logStep={spec.log_step}
      />
    );
  } else {
    widget = (
      <TextBox
        id={id}
        value={value === null ? null : String(value ?? '')}
        placeholder={placeholderOf(spec)}
        required={spec.required}
        onChange={onChange}
      />
    );
  }

  return (
    <Reveal
      open={isVisible}
      className={isWide(spec) ? 'col-span-2' : ''}
    >
      <FieldShell
        id={id}
        label={label}
        help={spec.help}
        problem={problem}
      >
        {widget}
      </FieldShell>
    </Reveal>
  );
}

interface FormCardProps {
  card: FormCardSpec;
  across: 2 | 3;
  parameters: Parameters;
  fields: ParameterSpec[];
  onChange: (name: string, value: ParameterValue) => void;
}

/**
 * One group of parameters in its card, side by side.
 */
function FormCard({
  card,
  across,
  parameters,
  fields,
  onChange,
}: FormCardProps) {
  const grid = across === 3 ? 'grid-cols-3' : 'grid-cols-2';
  return (
    <section className={CARD}>
      {card.title && <h4 className={CARD_TITLE}>{card.title}</h4>}
      <div className={`grid gap-x-3 ${grid}`}>
        {card.fields.map((spec) => (
          <ParameterField
            key={spec.name}
            spec={spec}
            value={parameters[spec.name] ?? null}
            isVisible={isShown(spec, parameters, fields)}
            onChange={(value) => onChange(spec.name, value)}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * A step's parameters, from what its task says about them: cards in two
 * columns, or one card across for a step with a single group, and what
 * is rarely changed folded under Advanced.
 */
export default function ParameterForm({
  parameters,
  onChange,
  specs,
}: ParameterFormProps) {
  const [isAdvancedOpen, setAdvancedOpen] = useState(false);
  const fields = useMemo(
    () => allFields(parameters, specs),
    [parameters, specs]
  );
  const cards = useMemo(
    () => cardsOf(fields.filter((spec) => !spec.advanced)),
    [fields]
  );
  const advanced = useMemo(
    () => fields.filter((spec) => spec.advanced),
    [fields]
  );

  if (fields.length === 0) {
    return <p className="text-xs text-slate-400">Nothing to set.</p>;
  }

  const setValue = (name: string, value: ParameterValue) =>
    onChange({ ...parameters, [name]: value });
  const shared = { parameters, fields, onChange: setValue };
  const isChanged = advanced.some((spec) => {
    const own = parameters[spec.name] ?? null;
    return own !== null && own !== spec.default;
  });

  return (
    <div className="flex flex-col gap-3">
      {cards.length === 1 ? (
        <FormCard
          card={cards[0]}
          across={3}
          {...shared}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 items-start">
          {intoColumns(cards).map((column, index) => (
            <div
              key={index}
              className="flex flex-col gap-3 min-w-0"
            >
              {column.map((card) => (
                <FormCard
                  key={card.title}
                  card={card}
                  across={acrossIn(card)}
                  {...shared}
                />
              ))}
            </div>
          ))}
        </div>
      )}
      {advanced.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={isAdvancedOpen}
            className={ADVANCED_BUTTON}
            onClick={() => setAdvancedOpen(!isAdvancedOpen)}
          >
            <ChevronRight
              size={13}
              className={`transition-transform ${
                isAdvancedOpen ? 'rotate-90' : ''
              }`}
            />
            <span>Advanced</span>
            {isChanged && (
              <span
                title="Something here is changed"
                className={CHANGED_DOT}
              />
            )}
          </button>
          <Reveal open={isAdvancedOpen}>
            <FormCard
              card={{ title: '', fields: advanced }}
              across={3}
              {...shared}
            />
          </Reveal>
        </>
      )}
    </div>
  );
}
