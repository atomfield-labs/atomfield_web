import { Sparkles } from 'lucide-react';
import { AI_BUTTON_LABEL } from '../../hooks/useAiReview';
import type { AiReviewControls } from '../../hooks/useAiReview';
import type { AiKeyState } from '../../types/api';

const BUTTON = [
  'py-1.5 px-3 rounded-lg bg-orange-600 hover:bg-orange-500 text-white',
  'text-xs font-semibold transition-colors shadow-2xs flex items-center',
  'gap-1.5 cursor-pointer shrink-0 disabled:bg-slate-200',
  'disabled:text-slate-500 disabled:cursor-default',
].join(' ');
const NEEDS_KEY = 'text-[11px] text-slate-500 truncate';
const KEY_LINK = 'text-orange-600 hover:text-orange-500 hover:underline';

/**
 * The button in a step's window. A step that already has an answer just
 * opens it: only "Ask again" in the tab spends the person's money again.
 */
export default function AiStepButton({
  aiKey,
  ai,
  onOpen,
}: {
  aiKey: AiKeyState | null;
  ai: AiReviewControls;
  onOpen: () => void;
}) {
  if (!ai.kind) return null;
  const canAsk = !!aiKey?.available && !!aiKey.saved;
  const press = () => {
    onOpen();
    if (!ai.review) void ai.start();
  };
  return (
    <>
      {aiKey && !aiKey.available && (
        <span className={NEEDS_KEY}>AI help is off on this server</span>
      )}
      {aiKey?.available && !aiKey.saved && (
        <a
          href="#account"
          className={`${NEEDS_KEY} ${KEY_LINK}`}
        >
          Add an AI key first
        </a>
      )}
      <button
        type="button"
        disabled={!canAsk || ai.starting}
        title={canAsk ? undefined : 'Add an AI key first'}
        className={BUTTON}
        onClick={press}
      >
        <Sparkles className="w-3.5 h-3.5" />
        <span>{AI_BUTTON_LABEL[ai.kind]}</span>
      </button>
    </>
  );
}
