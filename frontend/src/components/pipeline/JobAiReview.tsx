import { RotateCw, TriangleAlert } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { aiService } from '../../api/services';
import { AI_BUTTON_LABEL } from '../../hooks/useAiReview';
import type { AiReviewControls } from '../../hooks/useAiReview';
import type {
  AiKeyState,
  AiReview,
  AiSuggestion,
  AiVendorView,
} from '../../types/api';

const PANEL = 'h-full overflow-y-auto pr-2 flex flex-col gap-4';
const HEADING = 'mb-1.5 text-xs font-semibold text-slate-800';
const SUMMARY = 'text-sm font-medium text-slate-900 leading-relaxed';
const MUTED = 'text-xs text-slate-500 leading-relaxed';
const LINK = 'text-orange-600 hover:text-orange-500 hover:underline';
const WARNING = [
  'px-3 py-2 rounded-md bg-amber-50 border border-amber-200',
  'text-xs text-amber-900 leading-relaxed',
].join(' ');
const PROBLEM = 'text-sm text-red-600 leading-relaxed';
const ASK = [
  'self-start py-1.5 px-3 rounded-lg bg-orange-600 hover:bg-orange-500',
  'text-white text-xs font-semibold transition-colors cursor-pointer',
  'disabled:opacity-50 disabled:cursor-default',
].join(' ');
const ASK_AGAIN = [
  'py-1 px-2.5 border border-slate-200 bg-white hover:bg-slate-100',
  'text-slate-600 text-xs font-medium rounded-lg transition-colors',
  'flex items-center gap-1.5 cursor-pointer shrink-0',
  'disabled:opacity-50 disabled:cursor-default',
].join(' ');
const ROW = 'py-2 border-t border-slate-100 first:border-t-0 text-xs';
const ROW_FLAGGED = 'text-amber-800';
const VALUE = 'font-mono text-slate-800';
const SPINNER = [
  'w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full',
  'animate-spin',
].join(' ');
const WRITING = [
  'prose prose-sm prose-slate max-w-none',
  'prose-code:before:content-none prose-code:after:content-none',
].join(' ');
const REMARK_PLUGINS = [remarkGfm];
// The answer is a model's text, written after reading logs and web pages.
// An image's address could carry data out of this page by just loading,
// and a link could lead anywhere, so neither is drawn.
const NEVER_DRAWN = ['a', 'img'];
const ALL_OF_IT = 'all';

/**
 * A value as the screen shows it.
 */
function shownValue(value: unknown, unit?: string | null): string {
  const text = value === null || value === undefined ? 'not set' : `${value}`;
  return unit ? `${text} ${unit}` : text;
}

/**
 * One suggested setting. One the server couldn't accept still shows, with
 * why, so the person sees that the model got it wrong.
 */
function SuggestionRow({ item }: { item: AiSuggestion }) {
  if (item.problem) {
    return (
      <li className={`${ROW} ${ROW_FLAGGED}`}>
        <div className="flex items-center gap-1.5 font-medium">
          <TriangleAlert className="w-3.5 h-3.5 shrink-0" />
          <span className="font-mono">{item.setting}</span>
          <span className="font-mono">= {item.value}</span>
        </div>
        <p className="mt-0.5">{item.problem}</p>
      </li>
    );
  }
  return (
    <li className={ROW}>
      <div className="flex flex-wrap items-center gap-x-2">
        <span className="font-medium text-slate-800">
          {item.label || item.setting}
        </span>
        <span className={VALUE}>
          {shownValue(item.current, item.unit)} &rarr;{' '}
          {shownValue(item.value, item.unit)}
        </span>
      </div>
      <p className="mt-0.5 text-slate-600">{item.why}</p>
    </li>
  );
}

/**
 * What the model read, with every trim named, and how to see all of it.
 */
function WhatItRead({ jobId, review }: { jobId: string; review: AiReview }) {
  const read = (review.read_parts ?? []).map((part) =>
    part.shown === ALL_OF_IT ? part.name : `${part.name} (${part.shown})`
  );
  const unread = review.unread_pages ?? [];
  const left = review.left_behind ?? [];
  return (
    <div className={MUTED}>
      <p>
        Read: {read.join(', ') || 'only the step\'s settings and error'}.{' '}
        <a
          href={aiService.sentTextLink(jobId, review.id)}
          target="_blank"
          rel="noreferrer"
          className={LINK}
        >
          See what was sent
        </a>
      </p>
      {unread.length > 0 && (
        <p>Could not read: {unread.join(', ')}.</p>
      )}
      {left.length > 0 && (
        <p>
          Left on the cluster, so not read:{' '}
          {left.map((item) => item.name).join(', ')}.
        </p>
      )}
    </div>
  );
}

/**
 * Which model answered and what it took, the reminder, and asking again.
 */
function AnswerFooter({
  review,
  ai,
}: {
  review: AiReview;
  ai: AiReviewControls;
}) {
  return (
    <div className="flex items-end justify-between gap-3">
      <div className={MUTED}>
        {review.answered_by && (
          <p>
            Answered by {review.answered_by}.{' '}
            {review.input_tokens?.toLocaleString()} tokens in,{' '}
            {review.output_tokens?.toLocaleString()} out.
          </p>
        )}
        <p>AI can be wrong. Check before you run again.</p>
      </div>
      <button
        type="button"
        disabled={ai.starting}
        className={ASK_AGAIN}
        onClick={() => void ai.start()}
      >
        <RotateCw className="w-3 h-3" />
        <span>Ask again</span>
      </button>
    </div>
  );
}

/**
 * A finished answer.
 */
function Answer({
  jobId,
  review,
  ai,
}: {
  jobId: string;
  review: AiReview;
  ai: AiReviewControls;
}) {
  const suggestions = review.suggestions ?? [];
  const checks = review.check_next ?? [];
  return (
    <>
      <p className={SUMMARY}>{review.summary}</p>
      {suggestions.length > 0 && (
        <section>
          <h4 className={HEADING}>Try these settings</h4>
          <ul>
            {suggestions.map((item) => (
              <SuggestionRow
                key={item.setting}
                item={item}
              />
            ))}
          </ul>
        </section>
      )}
      {review.explanation && (
        <section>
          <h4 className={HEADING}>Why</h4>
          <div className={WRITING}>
            <ReactMarkdown
              remarkPlugins={REMARK_PLUGINS}
              skipHtml
              disallowedElements={NEVER_DRAWN}
              unwrapDisallowed
            >
              {review.explanation}
            </ReactMarkdown>
          </div>
        </section>
      )}
      {checks.length > 0 && (
        <section>
          <h4 className={HEADING}>Check next</h4>
          <ul className="list-disc pl-4 text-xs text-slate-700 space-y-0.5">
            {checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </section>
      )}
      <WhatItRead
        jobId={jobId}
        review={review}
      />
      <AnswerFooter
        review={review}
        ai={ai}
      />
    </>
  );
}

/**
 * What the person sees before anything is sent.
 */
function NotAskedYet({
  vendor,
  ai,
}: {
  vendor: AiVendorView;
  ai: AiReviewControls;
}) {
  return (
    <>
      <p className={MUTED}>
        This sends the step's log, inputs and settings to {vendor.title}, under
        your key.
      </p>
      {vendor.warning && <p className={WARNING}>{vendor.warning}</p>}
      <button
        type="button"
        disabled={ai.starting}
        className={ASK}
        onClick={() => void ai.start()}
      >
        {ai.kind && AI_BUTTON_LABEL[ai.kind]}
      </button>
    </>
  );
}

/**
 * A step's AI tab. It reads and suggests; nothing here changes a setting
 * or starts a run.
 */
export default function JobAiReview({
  jobId,
  aiKey,
  ai,
}: {
  jobId: string;
  aiKey: AiKeyState | null;
  ai: AiReviewControls;
}) {
  const { review } = ai;
  const saved = aiKey?.saved;
  const vendor = aiKey?.vendors.find((item) => item.id === saved?.vendor);
  const isRunning = review?.status === 'running';
  return (
    <div className={PANEL}>
      {aiKey && !aiKey.available && (
        <p className={MUTED}>AI help is off on this server.</p>
      )}
      {aiKey?.available && !saved && !review && (
        <p className={MUTED}>
          Add an AI key first, on your{' '}
          <a
            href="#account"
            className={LINK}
          >
            Account page
          </a>
          .
        </p>
      )}
      {vendor && !review && (
        <NotAskedYet
          vendor={vendor}
          ai={ai}
        />
      )}
      {isRunning && (
        <div className={`flex items-center gap-2 ${MUTED}`}>
          <span className={SPINNER} />
          <span>Reading this step's files...</span>
        </div>
      )}
      {review?.status === 'failed' && (
        <>
          <p
            role="alert"
            className={PROBLEM}
          >
            {review.error}
          </p>
          <AnswerFooter
            review={review}
            ai={ai}
          />
        </>
      )}
      {review?.status === 'done' && (
        <Answer
          jobId={jobId}
          review={review}
          ai={ai}
        />
      )}
      {ai.problem && (
        <p
          role="alert"
          className={PROBLEM}
        >
          {ai.problem}
        </p>
      )}
    </div>
  );
}
