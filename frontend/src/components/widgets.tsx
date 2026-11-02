import { useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';

/**
 * The app's standard form controls. Each is controlled: it shows the
 * value it is given and reports a new one. None knows what it is for,
 * so every form looks and behaves the same.
 */

const FRAME = [
  'flex items-stretch h-8 w-full min-w-0 rounded-md border bg-white',
  'transition-colors focus-within:ring-1 focus-within:ring-inset',
].join(' ');
const FRAME_CALM = [
  'border-slate-200 hover:border-orange-300',
  'focus-within:border-orange-500 focus-within:ring-orange-500',
].join(' ');
const FRAME_WRONG = [
  'border-red-400 focus-within:border-red-500',
  'focus-within:ring-red-500',
].join(' ');
const FIELD = [
  'flex-1 min-w-0 px-2 bg-transparent text-xs text-slate-800',
  'tabular-nums placeholder:text-slate-400 focus:outline-none',
].join(' ');
const UNIT = 'self-center pr-1.5 text-[11px] text-slate-400 select-none';
const ARROW = [
  'flex-1 flex items-center justify-center text-slate-400',
  'hover:bg-orange-50 hover:text-orange-600 transition-colors',
  'cursor-pointer disabled:opacity-30 disabled:cursor-default',
  'disabled:hover:bg-transparent disabled:hover:text-slate-400',
].join(' ');
const CHOICE = [
  'flex-1 min-w-0 px-1.5 rounded text-xs truncate transition-colors',
  'cursor-pointer',
].join(' ');
const CHOICE_IDLE = 'text-slate-500 hover:text-orange-600';
const CHOICE_ACTIVE = 'bg-white text-orange-600 font-medium shadow-2xs';
const FIXED = [
  'flex items-center h-8 px-2 rounded-md bg-slate-50',
  'text-xs text-slate-500 truncate',
].join(' ');
const SELECT = [
  'flex-1 min-w-0 pl-2 pr-6 bg-transparent text-xs text-slate-800',
  'appearance-none cursor-pointer focus:outline-none',
].join(' ');
const SWITCH = [
  'relative w-8 h-[18px] rounded-full transition-colors cursor-pointer',
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-300',
].join(' ');
const KNOB = [
  'absolute top-[2px] left-[2px] w-3.5 h-3.5 rounded-full bg-white',
  'shadow-2xs transition-transform',
].join(' ');
const INFO_BUTTON = 'shrink-0 text-slate-300 hover:text-slate-500';
const TOOLTIP = [
  'fixed z-[60] pointer-events-none w-64 p-3 rounded-lg bg-stone-900/95',
  'text-white text-xs shadow-xl',
].join(' ');
const TOOLTIP_WIDTH = 272;
const TOOLTIP_ROOM = 120;
const REVEAL = 'grid transition-[grid-template-rows,opacity] duration-200';
const REVEAL_OPEN = 'grid-rows-[1fr] opacity-100';
const REVEAL_SHUT = 'grid-rows-[0fr] opacity-0';
// Keeps sums like 0.1 + 0.2 from showing their rounding error.
const SIGNIFICANT_DIGITS = 12;
const LOG_STEP = 10;

export interface ChoiceOption {
  label: string;
  value: boolean | number | string | null;
}

interface NumberLimits {
  whole?: boolean;
  minimum?: number | null;
  maximum?: number | null;
  required?: boolean;
}

interface NumberBoxProps extends NumberLimits {
  id?: string;
  label?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  onProblem?: (problem: string | null) => void;
  step?: number | null;
  logStep?: boolean;
  // Where the arrows start from an empty box, and how big a step is.
  startFrom?: number | null;
  placeholder?: string;
  unit?: string | null;
}

/**
 * What is wrong with what has been typed, in a few words; null if it
 * is a value this box can take.
 */
function problemWith(text: string, limits: NumberLimits): string | null {
  if (text.trim() === '') return limits.required ? 'Required' : null;
  const typed = Number(text);
  if (!Number.isFinite(typed)) return 'Enter a number';
  if (limits.whole && !Number.isInteger(typed)) return 'Enter a whole number';
  if (limits.minimum != null && typed < limits.minimum) {
    return `At least ${limits.minimum}`;
  }
  if (limits.maximum != null && typed > limits.maximum) {
    return `At most ${limits.maximum}`;
  }
  return null;
}

/**
 * How far one press of an arrow moves a box: whole numbers by one,
 * others by the step asked for, else by the size of where they start.
 */
function arrowStep(props: NumberBoxProps): number {
  if (props.step) return props.step;
  if (props.whole || !props.startFrom) return 1;
  return 10 ** Math.floor(Math.log10(Math.abs(props.startFrom)));
}

function withinLimits(value: number, limits: NumberLimits): number {
  const floor = limits.minimum ?? -Infinity;
  return Math.min(limits.maximum ?? Infinity, Math.max(floor, value));
}

/**
 * Where one press of an arrow takes a box.
 */
function nextValue(direction: 1 | -1, props: NumberBoxProps): number {
  const base = props.value ?? props.startFrom ?? 0;
  const factor = direction > 0 ? LOG_STEP : 1 / LOG_STEP;
  const moved = props.logStep
    ? base * factor
    : base + direction * arrowStep(props);
  const exact = Number(moved.toPrecision(SIGNIFICANT_DIGITS));
  return withinLimits(exact, props);
}

/**
 * The little up and down buttons of a number box.
 */
function Arrows({
  onMove,
  atTop,
  atBottom,
}: {
  onMove: (direction: 1 | -1) => void;
  atTop: boolean;
  atBottom: boolean;
}) {
  // Pressing one must not take the keyboard away from the box.
  const keepFocus = (event: { preventDefault: () => void }) =>
    event.preventDefault();
  return (
    <div className="flex flex-col w-5 shrink-0 border-l border-slate-200">
      <button
        type="button"
        tabIndex={-1}
        aria-label="Up"
        disabled={atTop}
        className={`${ARROW} rounded-tr-[5px]`}
        onMouseDown={keepFocus}
        onClick={() => onMove(1)}
      >
        <ChevronUp size={11} />
      </button>
      <button
        type="button"
        tabIndex={-1}
        aria-label="Down"
        disabled={atBottom}
        className={`${ARROW} rounded-br-[5px]`}
        onMouseDown={keepFocus}
        onClick={() => onMove(-1)}
      >
        <ChevronDown size={11} />
      </button>
    </div>
  );
}

/**
 * A box for a number: type it, or use the arrows or the up and down
 * keys. What is typed stays as typed until it is a good value; leaving
 * the box goes back to the last good one.
 */
function NumberBox(props: NumberBoxProps) {
  const { id, label, value, onChange, onProblem, placeholder, unit } = props;
  const [draft, setDraft] = useState<string | null>(null);
  const problem = draft === null ? null : problemWith(draft, props);

  const type = (text: string) => {
    setDraft(text);
    const found = problemWith(text, props);
    onProblem?.(found);
    if (!found) onChange(text.trim() === '' ? null : Number(text));
  };
  const finish = () => {
    setDraft(null);
    onProblem?.(null);
  };
  const move = (direction: 1 | -1) => {
    finish();
    onChange(nextValue(direction, props));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') event.currentTarget.blur();
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    move(event.key === 'ArrowUp' ? 1 : -1);
  };

  return (
    <div className={`${FRAME} ${problem ? FRAME_WRONG : FRAME_CALM}`}>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        aria-label={label}
        aria-invalid={!!problem}
        value={draft ?? value ?? ''}
        placeholder={placeholder}
        className={FIELD}
        onChange={(event) => type(event.target.value)}
        onBlur={finish}
        onKeyDown={onKeyDown}
      />
      {unit && <span className={UNIT}>{unit}</span>}
      <Arrows
        onMove={move}
        atTop={value !== null && value === props.maximum}
        atBottom={value !== null && value === props.minimum}
      />
    </div>
  );
}

/**
 * A box for a whole number.
 */
export function SpinBox(props: Omit<NumberBoxProps, 'whole' | 'logStep'>) {
  return (
    <NumberBox
      {...props}
      whole
    />
  );
}

/**
 * A box for any number; ``1e-12`` can be typed.
 */
export function DoubleSpinBox(props: Omit<NumberBoxProps, 'whole'>) {
  return <NumberBox {...props} />;
}

/**
 * Three whole numbers held as one value, such as ``8 8 8``.
 */
export function MeshBox({
  id,
  label,
  parts,
  onChange,
  onProblem,
}: {
  id?: string;
  label: string;
  parts: number[];
  onChange: (value: string) => void;
  onProblem?: (problem: string | null) => void;
}) {
  const setPart = (at: number, part: number | null) => {
    if (part === null) return;
    const next = parts.map((old, index) => (index === at ? part : old));
    onChange(next.join(' '));
  };
  return (
    <div className="flex gap-1.5">
      {parts.map((part, index) => (
        <SpinBox
          key={index}
          id={index === 0 ? id : undefined}
          label={`${label} ${index + 1}`}
          value={part}
          minimum={1}
          required
          onChange={(value) => setPart(index, value)}
          onProblem={onProblem}
        />
      ))}
    </div>
  );
}

/**
 * A few short choices as joined buttons: all in sight, one click away.
 */
export function ChoiceButtons({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: ChoiceOption[];
  value: ChoiceOption['value'];
  onChange: (value: ChoiceOption['value']) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex h-8 gap-0.5 p-0.5 rounded-md bg-slate-100"
    >
      {options.map((option) => {
        const isChosen = option.value === value;
        return (
          <button
            key={option.label}
            type="button"
            title={option.label}
            aria-pressed={isChosen}
            className={`${CHOICE} ${isChosen ? CHOICE_ACTIVE : CHOICE_IDLE}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The only choice there is: shown, with nothing to change.
 */
export function FixedValue({ text }: { text: string }) {
  return <div className={FIXED}>{text}</div>;
}

/**
 * A menu, for choices too many or too long to show as buttons.
 */
export function Dropdown({
  id,
  options,
  value,
  onChange,
}: {
  id?: string;
  options: ChoiceOption[];
  value: ChoiceOption['value'];
  onChange: (value: ChoiceOption['value']) => void;
}) {
  const chosen = options.findIndex((option) => option.value === value);
  return (
    <div className={`${FRAME} ${FRAME_CALM} relative`}>
      <select
        id={id}
        value={chosen}
        className={SELECT}
        onChange={(event) => onChange(options[+event.target.value].value)}
      >
        {options.map((option, index) => (
          <option
            key={option.label}
            value={index}
          >
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={13}
        className="absolute right-1.5 top-2 text-slate-400 pointer-events-none"
      />
    </div>
  );
}

/**
 * An on and off switch.
 */
export function Toggle({
  id,
  value,
  onChange,
}: {
  id?: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  const track = value ? 'bg-orange-500' : 'bg-slate-200';
  return (
    <div className="flex items-center gap-2 h-8">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={value}
        className={`${SWITCH} ${track}`}
        onClick={() => onChange(!value)}
      >
        <span
          className={`${KNOB} ${value ? 'translate-x-3.5' : 'translate-x-0'}`}
        />
      </button>
      <span className="text-xs text-slate-500 select-none">
        {value ? 'On' : 'Off'}
      </span>
    </div>
  );
}

/**
 * A box for text. An empty one is a value of null.
 */
export function TextBox({
  id,
  value,
  onChange,
  placeholder,
  required,
  secret,
}: {
  id?: string;
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  required?: boolean;
  // Shown as dots, and not offered for saving as a password.
  secret?: boolean;
}) {
  const wrong = required && !value;
  return (
    <div className={`${FRAME} ${wrong ? FRAME_WRONG : FRAME_CALM}`}>
      <input
        id={id}
        type={secret ? 'password' : 'text'}
        autoComplete={secret ? 'new-password' : 'off'}
        spellCheck={false}
        value={value ?? ''}
        placeholder={placeholder}
        className={FIELD}
        onChange={(event) => onChange(event.target.value || null)}
      />
    </div>
  );
}

/**
 * The faint i that says more when pointed at, as in the task list.
 */
export function InfoTip({ text, about }: { text: string; about: string }) {
  const [place, setPlace] = useState<{ x: number; y: number } | null>(null);
  const show = (target: Element) => {
    const box = target.getBoundingClientRect();
    setPlace({
      x: Math.min(box.left, window.innerWidth - TOOLTIP_WIDTH),
      y: Math.min(box.bottom + 6, window.innerHeight - TOOLTIP_ROOM),
    });
  };
  return (
    <>
      <button
        type="button"
        tabIndex={-1}
        aria-label={`About ${about}`}
        className={INFO_BUTTON}
        onMouseEnter={(event) => show(event.currentTarget)}
        onMouseLeave={() => setPlace(null)}
      >
        <Info size={12} />
      </button>
      {/* The modal is moved by a transform, which would carry a fixed
          tooltip with it and clip it: this one lives outside it. */}
      {place &&
        createPortal(
          <div
            role="tooltip"
            className={TOOLTIP}
            style={{ left: place.x, top: place.y }}
          >
            {text}
          </div>,
          document.body
        )}
    </>
  );
}

/**
 * A control's label above it, with its help, or what is wrong with
 * what was typed. Saying that here keeps the form from jumping.
 */
export function FieldShell({
  id,
  label,
  help,
  problem,
  children,
}: {
  id?: string;
  label: string;
  help?: string | null;
  problem?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="pb-2.5">
      <div className="flex items-center justify-between gap-2 h-4 mb-1">
        <label
          htmlFor={id}
          title={label}
          className="text-[11px] font-medium text-slate-600 truncate"
        >
          {label}
        </label>
        {problem ? (
          <span className="text-[10px] text-red-600 truncate">{problem}</span>
        ) : (
          help && (
            <InfoTip
              text={help}
              about={label}
            />
          )
        )}
      </div>
      {children}
    </div>
  );
}

/**
 * Opens and closes smoothly, so what is below it glides rather than
 * jumps. While shut, nothing in it can take the keyboard.
 */
export function Reveal({
  open,
  className = '',
  children,
}: {
  open: boolean;
  className?: string;
  children: ReactNode;
}) {
  const look = open ? REVEAL_OPEN : REVEAL_SHUT;
  return (
    <div
      className={`${REVEAL} ${look} ${className}`}
      inert={!open}
    >
      <div className="overflow-hidden min-h-0">{children}</div>
    </div>
  );
}
