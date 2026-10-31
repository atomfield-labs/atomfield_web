// The look the card pages share (sessions, labs): white cards that turn
// orange under the pointer, and an orange dashed card to add one.

export const PAGE = 'w-full min-h-screen bg-slate-50 p-8 pt-24';
export const PAGE_WIDTH = 'max-w-6xl mx-auto';
export const PAGE_TITLE = 'text-3xl font-extrabold text-slate-800';
export const CARD_GRID = 'grid grid-cols-1 md:grid-cols-3 gap-6';

export const NEW_CARD = [
  'flex flex-col items-center justify-center min-h-[160px] p-6 group',
  'border-2 border-dashed border-orange-200 rounded-xl cursor-pointer',
  'hover:border-orange-500 hover:bg-orange-50/40 transition-colors',
].join(' ');
export const NEW_CARD_PLUS = [
  'w-12 h-12 mb-3 rounded-full bg-orange-50 group-hover:bg-orange-100',
  'flex items-center justify-center transition-colors',
].join(' ');
export const NEW_CARD_SIGN =
  'text-2xl font-bold text-orange-400 group-hover:text-orange-600';
export const NEW_CARD_TITLE = [
  'text-lg font-bold text-slate-700 group-hover:text-orange-600',
  'transition-colors',
].join(' ');

export const CARD = [
  'flex flex-col h-full min-h-[160px] p-6 bg-white rounded-xl',
  'border border-slate-200 group-hover:border-orange-400',
  'transition-colors',
].join(' ');
export const CARD_TITLE = [
  'mb-4 text-lg font-bold text-slate-800 group-hover:text-orange-600',
  'transition-colors line-clamp-1',
].join(' ');
export const CARD_FACTS = [
  'mt-auto pt-3 border-t border-slate-100 text-xs font-medium',
  'text-slate-500',
].join(' ');

// A way to remove something: shows under the pointer, or always where
// nothing can hover.
export const ON_HOVER = [
  'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
  'pointer-coarse:opacity-100',
].join(' ');
