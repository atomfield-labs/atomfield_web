import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Download, Upload, X } from 'lucide-react';
import { describeError } from '../../api/client';
import { jobsService } from '../../api/services';
import { useTaskDefinitions } from '../../hooks/useTaskDefinitions';
import type { InputFiles } from '../../types/api';
import { triggerFileDownload } from '../../utils/downloadHelper';
import { STATUS_TEXT, statusLook } from '../../utils/jobStatus';
import { INPUT_FILE_TYPES } from '../../utils/structureParser';
import StatusIcon from '../StatusIcon';
import ParameterForm, { FIELD_NAME } from './ParameterForm';
import RunFilesButton from './RunFilesButton';

const TABS = [
  { id: 'parameters', label: 'Parameters' },
  { id: 'log', label: 'Log' },
  { id: 'files', label: 'Files' },
] as const;
type Tab = (typeof TABS)[number]['id'];

const PANEL = [
  'absolute md:relative inset-y-0 right-0 z-20 w-[340px] max-w-full',
  'shrink-0 flex flex-col bg-white border-l border-stone-200',
].join(' ');
const CLOSE = [
  'p-2.5 rounded-[10px] text-stone-500 hover:text-stone-800',
  'hover:bg-stone-100 cursor-pointer',
].join(' ');
const TAB = 'h-10 -mb-px border-b-2 text-sm cursor-pointer';
const TAB_ON = 'border-orange-700 font-medium text-stone-900';
const TAB_OFF = 'border-transparent text-stone-500 hover:text-stone-800';
const SUBTITLE = 'flex items-center gap-1.5 text-[13px] text-stone-600';
const TEXT_BOX = [
  'h-full m-0 p-3 rounded-[10px] bg-stone-50 border border-stone-200',
  'font-mono text-xs leading-relaxed text-stone-800 overflow-auto',
  'whitespace-pre-wrap break-words select-text',
].join(' ');
const READ_ONLY = [
  'min-h-10 px-3 py-2 rounded-[10px] border border-stone-200 bg-stone-50',
  'font-mono text-[13px] text-stone-500 break-all',
].join(' ');
const FOOTER = [
  'min-h-12 flex items-center justify-between gap-3 px-4 py-2',
  'border-t border-stone-200',
].join(' ');
const DANGER = [
  'text-sm font-medium text-red-700 hover:underline cursor-pointer',
  'disabled:text-stone-500 disabled:no-underline disabled:cursor-default',
].join(' ');
const REMOVE = 'text-sm text-stone-500 hover:text-red-700 cursor-pointer';
const COPIES_ROW = [
  'flex items-center justify-between gap-3 pt-3.5 border-t border-stone-100',
].join(' ');
const COPIES_INPUT = [
  'h-10 w-20 px-3 rounded-[10px] border border-stone-200 bg-white text-right',
  'font-mono text-[13px] text-stone-900 focus:outline-none',
  'focus:border-orange-700 disabled:bg-stone-50 disabled:text-stone-500',
].join(' ');
const MAX_COPIES = 500;
const QUIET = [
  'flex items-center gap-1.5 text-sm text-stone-600',
  'hover:text-stone-900 cursor-pointer',
].join(' ');

interface StepPanelProps {
  // The chosen box on the canvas; nothing shows while it is null.
  node: any | null;
  onClose: () => void;
  onDelete: () => void;
  onUpdateParameters: (parameters: Record<string, any>) => void;
  onSetCopies: (count: number) => void;
  // The run the box belongs to, for getting its files.
  runId: string | null;
}

type DetailsProps = Omit<StepPanelProps, 'node'> & { node: any };

/**
 * Whether a box holds an input file, rather than a step.
 */
function isInputFile(node: any): boolean {
  const data = node.data;
  return (
    node.type === 'structure' ||
    data?.type === 'structure' ||
    Boolean(data?.workspace_path || node.workspace_path)
  );
}

/**
 * What a run produced is listed by name, however it was recorded.
 */
function artifactName(artifact: any): string {
  return typeof artifact === 'string'
    ? artifact
    : artifact.name || artifact.path;
}

function PanelHeader({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-2 pl-4 pr-1.5 pt-2">
      <div className="min-w-0 flex flex-col gap-1 pt-2 pb-2">
        <h2 className="text-base font-semibold text-stone-900 break-words">
          {title}
        </h2>
        {children}
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className={CLOSE}
      >
        <X size={18} />
      </button>
    </header>
  );
}

function TabBar({ tab, onTab }: { tab: Tab; onTab: (tab: Tab) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Step details"
      className="flex gap-[18px] px-4 border-b border-stone-200"
    >
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={tab === id}
          onClick={() => onTab(id)}
          className={`${TAB} ${tab === id ? TAB_ON : TAB_OFF}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * How many times a step runs side by side; a change counts once the
 * person leaves the field or presses Enter.
 */
function ParallelCopies({
  copies,
  locked,
  onSet,
}: {
  copies: number;
  locked: boolean;
  onSet: (count: number) => void;
}) {
  const commit = (typed: string) => {
    const count = Math.min(MAX_COPIES, Math.max(1, Number(typed) || 1));
    if (count !== copies) onSet(count);
  };
  return (
    <div className={COPIES_ROW}>
      <label htmlFor="step-copies" className={FIELD_NAME}>
        Parallel copies
      </label>
      <input
        id="step-copies"
        key={copies}
        type="number"
        min={1}
        max={MAX_COPIES}
        defaultValue={copies}
        disabled={locked}
        onBlur={(event) => commit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') commit(event.currentTarget.value);
        }}
        className={COPIES_INPUT}
      />
    </div>
  );
}

function FilesTab({
  artifacts,
  runId,
}: {
  artifacts: any[];
  runId: string | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      {artifacts.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {artifacts.map((artifact, index) => (
            <li key={index} className={READ_ONLY}>
              {artifactName(artifact)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-stone-500">No files yet.</p>
      )}
      {runId && <RunFilesButton runId={runId} />}
    </div>
  );
}

/**
 * A step: how it stands, then its parameters, log and files. Its
 * parameters are locked while it runs or waits to.
 */
function StepDetails({
  node,
  onClose,
  onDelete,
  onUpdateParameters,
  onSetCopies,
  runId,
}: DetailsProps) {
  const [tab, setTab] = useState<Tab>('parameters');
  const [problem, setProblem] = useState<string | null>(null);
  // A running job stops only once its agent acts on the request.
  const [cancelling, setCancelling] = useState<string | null>(null);
  const { taskById } = useTaskDefinitions();
  const data = node.data ?? {};
  const look = statusLook(node.status ?? data.status);
  const live = look === 'running' || look === 'waiting';
  const jobId: string | undefined = node.job_id ?? data.job_id;
  const parameters = node.parameters ?? data.parameters ?? {};
  const defaults =
    node.default_parameters ??
    data.default_parameters ??
    data.originalData?.default_parameters ??
    {};
  const wired: InputFiles = data.inputs ?? node.inputs ?? {};
  const inputs = Object.entries(wired);

  const cancel = async () => {
    if (!jobId) return;
    setProblem(null);
    setCancelling(jobId);
    try {
      await jobsService.cancelJob(jobId);
    } catch (error) {
      setCancelling(null);
      setProblem(describeError(error, 'Could not cancel the step.'));
    }
  };

  return (
    <>
      <PanelHeader
        title={data.label || node.script_name || 'Step'}
        onClose={onClose}
      >
        <span className={SUBTITLE}>
          <StatusIcon status={node.status ?? data.status} size={14} />
          {STATUS_TEXT[look]}
        </span>
      </PanelHeader>
      <TabBar tab={tab} onTab={setTab} />
      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {tab === 'parameters' && (
          <div className="flex flex-col gap-3.5">
            {live && (
              <span className="text-[13px] text-stone-500">
                Locked while running.
              </span>
            )}
            {inputs.map(([port, files]) => (
              <div key={port} className="flex flex-col gap-1.5">
                <span className={FIELD_NAME}>{port.replaceAll('_', ' ')}</span>
                <div className={READ_ONLY}>{files.join(', ')}</div>
              </div>
            ))}
            <ParameterForm
              parameters={parameters}
              specs={taskById.get(data.task_id ?? node.task_id)?.parameters}
              locked={live}
              onChange={onUpdateParameters}
            />
            <ParallelCopies
              copies={node.copies ?? 1}
              locked={live}
              onSet={onSetCopies}
            />
          </div>
        )}
        {tab === 'log' && (
          <pre className={TEXT_BOX}>
            {node.logs || data.logs || 'No output yet.'}
          </pre>
        )}
        {tab === 'files' && (
          <FilesTab
            artifacts={node.artifacts ?? data.artifacts ?? []}
            runId={runId}
          />
        )}
      </div>
      {problem && (
        <p role="alert" className="px-4 pb-2 text-[13px] text-red-700">
          {problem}
        </p>
      )}
      <footer className={FOOTER}>
        {live ? (
          jobId && (
            <button
              type="button"
              onClick={cancel}
              disabled={cancelling === jobId}
              className={DANGER}
            >
              {cancelling === jobId ? 'Cancelling…' : 'Cancel step'}
            </button>
          )
        ) : (
          <button type="button" onClick={onDelete} className={REMOVE}>
            Remove step
          </button>
        )}
        {!live && tab === 'parameters' && Object.keys(defaults).length > 0 && (
          <button
            type="button"
            onClick={() => onUpdateParameters({ ...defaults })}
            className={QUIET}
          >
            Reset to defaults
          </button>
        )}
      </footer>
    </>
  );
}

/**
 * An input file: what is in it, and ways to get or replace it.
 */
function InputFileDetails({ node, onClose, onDelete }: DetailsProps) {
  const picker = useRef<HTMLInputElement>(null);
  const data = node.data ?? node;
  const filename: string = data.filename || 'Input file';
  const content: string = data.raw_content || '';
  const lines =
    data.line_count || content.split(/\r?\n/).filter(Boolean).length;
  const kilobytes = ((data.size_bytes ?? 0) / 1024).toFixed(1);

  return (
    <>
      <PanelHeader title={filename} onClose={onClose}>
        <span className={SUBTITLE}>
          {content ? `${lines} lines · ${kilobytes} KB` : 'No file yet'}
        </span>
      </PanelHeader>
      <div className="flex-1 min-h-0 p-4 pt-2">
        <pre className={TEXT_BOX}>{content || 'Drop a file on the box.'}</pre>
      </div>
      <footer className={FOOTER}>
        <button type="button" onClick={onDelete} className={REMOVE}>
          Remove
        </button>
        <div className="flex items-center gap-4">
          <input
            ref={picker}
            type="file"
            hidden
            accept={INPUT_FILE_TYPES}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) data.onFileUpload?.(node.id, file);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => picker.current?.click()}
            className={QUIET}
          >
            <Upload size={14} />
            Replace
          </button>
          {content && (
            <button
              type="button"
              onClick={() =>
                triggerFileDownload(content, filename, 'text/plain')
              }
              className={QUIET}
            >
              <Download size={14} />
              Download
            </button>
          )}
        </div>
      </footer>
    </>
  );
}

/**
 * The side panel beside the canvas: the chosen box's details. Close it
 * with its X, Escape, or a click on the empty canvas.
 */
export default function StepPanel({ node, ...actions }: StepPanelProps) {
  const isOpen = Boolean(node);
  const { onClose } = actions;

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isOpen, onClose]);

  if (!node) return null;
  const Details = isInputFile(node) ? InputFileDetails : StepDetails;
  return (
    <aside aria-label="Step" className={PANEL}>
      <Details node={node} {...actions} />
    </aside>
  );
}
