import { useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import 'highlight.js/styles/github-dark.css';
import type { Guide } from '../../content/guides';

const TEXT = [
  'prose prose-slate max-w-none prose-headings:tracking-tight',
  'prose-h1:text-[1.75rem] sm:prose-h1:text-4xl',
  'prose-a:text-orange-600 hover:prose-a:text-orange-500',
  'prose-pre:bg-slate-900 prose-pre:pr-20 prose-pre:text-[13px]',
  'prose-code:before:content-none prose-code:after:content-none',
  '[&_:not(pre)>code]:bg-slate-100 [&_:not(pre)>code]:px-1',
  '[&_:not(pre)>code]:py-0.5 [&_:not(pre)>code]:rounded',
  '[&_:not(pre)>code]:font-medium [&_:not(pre)>code]:text-slate-800',
  '[&_:not(pre)>code]:break-words',
].join(' ');
const COPY = [
  'absolute top-2 right-2 flex items-center gap-1 h-7 px-2 rounded-md',
  'bg-slate-800 text-xs text-slate-300 hover:text-white cursor-pointer',
  'transition-colors',
].join(' ');
const COPIED_MS = 1500;
const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];
// How one guide names another: `docs/releases.md` or `releases.md`.
const GUIDE_FILE = /^(?:docs\/)?([a-z-]+)\.md$/;

/**
 * A block of code with a button to copy it, where the browser allows.
 */
function CodeBlock({ children }: { children?: ReactNode }) {
  const block = useRef<HTMLPreElement>(null);
  const [isCopied, setIsCopied] = useState(false);
  const copy = async () => {
    const text = block.current?.innerText ?? '';
    await navigator.clipboard.writeText(text.trimEnd());
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), COPIED_MS);
  };
  const Icon = isCopied ? Check : Copy;
  return (
    <div className="relative my-5">
      <pre
        ref={block}
        className="my-0!"
      >
        {children}
      </pre>
      {navigator.clipboard && (
        <button
          type="button"
          onClick={() => void copy()}
          className={COPY}
        >
          <Icon size={12} />
          {isCopied ? 'Copied' : 'Copy'}
        </button>
      )}
    </div>
  );
}

/**
 * A guide's markdown as the page shows it. A guide naming another this
 * reader may open becomes a link to it, by its title.
 */
export default function GuideText({
  markdown,
  guides,
}: {
  markdown: string;
  guides: Guide[];
}) {
  const components = useMemo<Components>(
    () => ({
      pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
      table: ({ children }) => (
        <div className="overflow-x-auto">
          <table>{children}</table>
        </div>
      ),
      code: ({ children, className }) => {
        const id = String(children).match(GUIDE_FILE)?.[1];
        const guide = guides.find((item) => item.id === id);
        if (!guide) return <code className={className}>{children}</code>;
        return <a href={`#docs/${guide.id}`}>{guide.title}</a>;
      },
    }),
    [guides]
  );
  return (
    <div className={TEXT}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={components}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
