import { useRef } from 'react';
import { Upload } from 'lucide-react';
import { usePipelineTemplates } from '../../hooks/usePipelineTemplates';
import type { PipelineTemplate } from '../../types/api';
import { INPUT_FILE_TYPES } from '../../utils/structureParser';
import { layoutTemplate } from '../../utils/templates';

// A template drawn small: its boxes in running order, and their links.
const GLYPH_WIDTH = 88;
const GLYPH_HEIGHT = 32;
const BOX_WIDTH = 14;
const BOX_HEIGHT = 8;
const COLUMN_GAP = 4;
const ROW_GAP = 3;

const COLUMN = 'm-auto w-full max-w-[600px] flex flex-col items-center gap-6';
const HEADING = 'text-[22px] font-semibold tracking-tight text-stone-900';
const GRID = [
  'pointer-events-auto w-full grid gap-3',
  'grid-cols-[repeat(auto-fit,minmax(170px,1fr))]',
].join(' ');
const BROWSE = [
  'pointer-events-auto text-orange-600 underline-offset-2 hover:underline',
  'cursor-pointer',
].join(' ');
const CARD = [
  'flex flex-col items-start gap-4 p-4 rounded-xl bg-white text-left',
  'border border-stone-200 hover:border-orange-400 hover:bg-orange-50',
  'cursor-pointer transition-colors',
  'shadow-[0_1px_2px_rgba(28,25,23,0.04)]',
].join(' ');
const DROP_ZONE = [
  'w-full flex items-center justify-center gap-2.5 min-h-16 px-4 py-3',
  'rounded-xl border-[1.5px] border-dashed border-stone-300 text-stone-600',
].join(' ');

interface Point {
  x: number;
  y: number;
}

interface Glyph {
  boxWidth: number;
  boxes: Point[];
  links: [Point, Point][];
}

/**
 * Where each box of a template sits in its small drawing: one column
 * per step of running order, each column centred.
 */
function glyphOf(template: PipelineTemplate): Glyph {
  const columns = new Map<number, { key: string; y: number }[]>();
  for (const [key, position] of layoutTemplate(template)) {
    const column = columns.get(position.x) ?? [];
    column.push({ key, y: position.y });
    columns.set(position.x, column);
  }
  const xs = [...columns.keys()].sort((left, right) => left - right);
  const room = (GLYPH_WIDTH - (xs.length - 1) * COLUMN_GAP) / xs.length;
  const boxWidth = Math.min(BOX_WIDTH, room);
  const step = xs.length > 1 ? (GLYPH_WIDTH - boxWidth) / (xs.length - 1) : 0;
  const placed = new Map<string, Point>();
  xs.forEach((x, column) => {
    const keys = columns.get(x)!.sort((left, right) => left.y - right.y);
    const height = keys.length * (BOX_HEIGHT + ROW_GAP) - ROW_GAP;
    const top = (GLYPH_HEIGHT - height) / 2;
    const left = xs.length > 1 ? column * step : (GLYPH_WIDTH - boxWidth) / 2;
    keys.forEach(({ key }, row) =>
      placed.set(key, { x: left, y: top + row * (BOX_HEIGHT + ROW_GAP) })
    );
  });
  const links = template.steps.flatMap((item) =>
    item.after
      .filter((key) => placed.has(key) && placed.has(item.key))
      .map((key): [Point, Point] => [placed.get(key)!, placed.get(item.key)!])
  );
  return { boxWidth, boxes: [...placed.values()], links };
}

/**
 * A curve from the right of one box to the left of the next.
 */
function linkPath(from: Point, to: Point, boxWidth: number): string {
  const start = { x: from.x + boxWidth, y: from.y + BOX_HEIGHT / 2 };
  const end = { x: to.x, y: to.y + BOX_HEIGHT / 2 };
  const middle = (start.x + end.x) / 2;
  return (
    `M${start.x} ${start.y}C${middle} ${start.y} ` +
    `${middle} ${end.y} ${end.x} ${end.y}`
  );
}

function TemplateGlyph({ template }: { template: PipelineTemplate }) {
  const { boxWidth, boxes, links } = glyphOf(template);
  return (
    <svg
      aria-hidden="true"
      width={GLYPH_WIDTH}
      height={GLYPH_HEIGHT}
      viewBox={`0 0 ${GLYPH_WIDTH} ${GLYPH_HEIGHT}`}
      fill="none"
    >
      {links.map(([from, to]) => (
        <path
          key={`${from.x}-${from.y}-${to.x}-${to.y}`}
          d={linkPath(from, to, boxWidth)}
          stroke="#D6D3D1"
          strokeWidth="1.5"
        />
      ))}
      {boxes.map((box) => (
        <rect
          key={`${box.x}-${box.y}`}
          x={box.x}
          y={box.y}
          width={boxWidth}
          height={BOX_HEIGHT}
          rx="2.5"
          fill="#FFFFFF"
          stroke="#A8A29E"
          strokeWidth="1.25"
        />
      ))}
    </svg>
  );
}

/**
 * What an empty canvas shows: the catalog's templates, and a place to
 * drop the files a pipeline starts from. Dropped files and dragged
 * tasks pass through to the canvas underneath.
 */
export default function StartScreen({
  onLoadTemplate,
  onFiles,
}: {
  onLoadTemplate: (template: PipelineTemplate) => void;
  onFiles: (files: File[]) => void;
}) {
  const templates = usePipelineTemplates();
  const picker = useRef<HTMLInputElement>(null);
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex p-6">
      <div className={COLUMN}>
        <div className="text-center">
          <h2 className={HEADING}>Start a pipeline</h2>
          <p className="text-stone-500">Pick a template, or drag tasks here.</p>
        </div>
        {templates.length > 0 && (
          <div className={GRID}>
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => onLoadTemplate(template)}
                className={CARD}
              >
                <TemplateGlyph template={template} />
                <span className="flex flex-col gap-0.5">
                  <span className="font-medium text-stone-900">
                    {template.title}
                  </span>
                  <span className="text-[13px] text-stone-500">
                    {template.steps.length}{' '}
                    {template.steps.length === 1 ? 'step' : 'steps'}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
        <div className={DROP_ZONE}>
          <Upload size={18} aria-hidden="true" />
          <span>
            Drop input files or{' '}
            <button
              type="button"
              onClick={() => picker.current?.click()}
              className={BROWSE}
            >
              browse
            </button>
          </span>
          <input
            ref={picker}
            type="file"
            multiple
            hidden
            accept={INPUT_FILE_TYPES}
            onChange={(event) => {
              onFiles([...(event.target.files ?? [])]);
              event.target.value = '';
            }}
          />
        </div>
      </div>
    </div>
  );
}
