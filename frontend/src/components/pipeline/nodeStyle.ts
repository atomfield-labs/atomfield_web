import { Position } from '@xyflow/react';

// The look every box on the canvas shares: white at rest, light orange
// under the pointer, ringed in orange when selected.

export const HANDLE_CLASS = [
  '!w-2 !h-2 !bg-white !border-[1.5px] !border-stone-300',
  'z-10 cursor-crosshair',
].join(' ');

const BOX = [
  'relative w-[180px] h-[52px] flex items-center gap-2.5 px-3',
  'rounded-[10px] bg-white hover:bg-orange-50 select-none',
  'transition-colors',
].join(' ');
const SELECTED = [
  'border-[1.5px] border-orange-600',
  'shadow-[0_0_0_2px_rgba(234,88,12,0.35),0_4px_12px_-2px_rgba(234,88,12,0.2)]',
].join(' ');
const RESTING = [
  'border border-stone-200 hover:border-orange-400',
  'shadow-[0_1px_2px_rgba(28,25,23,0.05)]',
].join(' ');
const DASHED =
  'border border-dashed border-stone-300 hover:border-orange-400';

/**
 * Classes for a box on the canvas: ringed when selected, dashed when
 * it waits (to start, or for a file).
 */
export function nodeBox(selected: boolean, dashed = false): string {
  const edge = selected ? SELECTED : dashed ? DASHED : RESTING;
  return `${BOX} ${edge}`;
}

// A step's link points: every side takes links in and out, so
// pipelines can run any way. The ids are stored in saved pipelines.
export const STEP_HANDLES = [
  { id: 'source-right', type: 'source', position: Position.Right },
  { id: 'target-left', type: 'target', position: Position.Left },
  { id: 'target-top', type: 'target', position: Position.Top },
  { id: 'source-top', type: 'source', position: Position.Top },
  { id: 'source-bottom', type: 'source', position: Position.Bottom },
  { id: 'target-bottom', type: 'target', position: Position.Bottom },
  { id: 'source-left', type: 'source', position: Position.Left },
  { id: 'target-right', type: 'target', position: Position.Right },
] as const;
