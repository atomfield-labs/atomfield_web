import {
  lazy,
  Suspense,
  useState,
  useEffect,
  useRef,
  useCallback,
} from 'react';
import { X, Trash2, Download, RotateCcw, FileText, Upload } from 'lucide-react';
import { triggerFileDownload } from '../../utils/downloadHelper';
import { INPUT_FILE_TYPES } from '../../utils/structureParser';
import JobArtifacts from './JobArtifacts';
import JobPlots from './JobPlots';
import RunFilesButton from './RunFilesButton';
import ParameterForm from './ParameterForm';
import AiStepButton from './AiStepButton';
import { useAiKey } from '../../hooks/useAiKey';
import { useAiReview } from '../../hooks/useAiReview';
import { useTaskDefinitions } from '../../hooks/useTaskDefinitions';
import { defaultParameterValues } from '../../utils/taskCatalog';
import type { InputFiles } from '../../types/api';

// It brings a Markdown renderer, so it loads only when it is opened.
const JobAiReview = lazy(() => import('./JobAiReview'));
const AI_TAB_LOADING = <p className="text-xs text-slate-400">Loading...</p>;

const WIRED_ROW_CLASS = [
  'p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center',
  'justify-between text-xs font-mono shrink-0',
].join(' ');

const TILE_CLASS = [
  'w-9 h-9 rounded-lg border flex items-center justify-center',
  'shrink-0',
].join(' ');

const FILE_TILE_CLASS = 'bg-orange-50 text-orange-600 border-orange-200';

const STEP_TILE_CLASS = 'bg-slate-100 text-slate-600 border-slate-200';

// The output a task names when its script leaves plots to draw.
const PLOTS_OUTPUT = 'plots';

const TAB_BUTTON =
  'py-2.5 font-semibold transition-colors border-b-2 -mb-px cursor-pointer';
const TAB_ACTIVE = 'text-orange-600 border-orange-500';
const TAB_IDLE = 'text-slate-500 hover:text-slate-800 border-transparent';

const FOOTER_BUTTON = [
  'py-1.5 px-3 border border-slate-200 bg-white hover:bg-slate-100',
  'text-slate-600 text-xs font-medium rounded-lg transition-colors',
  'flex items-center gap-1.5 cursor-pointer shadow-2xs',
].join(' ');

interface TabButtonProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

/**
 * One tab of a step's modal.
 */
function TabButton({ label, isActive, onClick }: TabButtonProps) {
  return (
    <button
      type="button"
      className={`${TAB_BUTTON} ${isActive ? TAB_ACTIVE : TAB_IDLE}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

// One size whatever the tab, unless the window is too short to hold it.
const MODAL_BODY = [
  'h-[min(480px,calc(100vh-184px))]',
  'p-6 overflow-hidden flex flex-col',
].join(' ');

interface InspectorDrawerProps {
  node: any | null;
  onClose: () => void;
  onDelete?: () => void;
  onUpdateParameters?: (newParams: Record<string, any>) => void;
  defaultParameters?: Record<string, any>;
  // The run the node belongs to, for downloading its files.
  runId?: string | null;
}

export default function InspectorDrawer({
  node: propNode,
  onClose,
  onDelete,
  onUpdateParameters,
  defaultParameters,
  runId,
}: InspectorDrawerProps) {
  const [cachedNode, setCachedNode] = useState(propNode);
  const [isMounted, setIsMounted] = useState(!!propNode);
  const [isAnimatingIn, setIsAnimatingIn] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Tabs for script nodes: params | logs | plots | artifacts | ai
  const [scriptTab, setScriptTab] = useState<
    'params' | 'logs' | 'plots' | 'artifacts' | 'ai'
  >('params');
  const { taskById } = useTaskDefinitions();
  const shownNode = propNode || cachedNode;
  const jobId: string | undefined =
    shownNode?.job_id ?? shownNode?.data?.job_id;
  const stepStatus: string | undefined =
    shownNode?.status ?? shownNode?.data?.status;
  const { state: aiKey } = useAiKey();
  const ai = useAiReview(jobId, stepStatus);

  const handleClose = useCallback(() => {
    setIsAnimatingIn(false);
    onClose();
  }, [onClose]);

  // Synchronize propNode with local display and open/close animation
  useEffect(() => {
    if (propNode) {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setCachedNode(propNode);
      setIsMounted(true);
      const raf1 = requestAnimationFrame(() => {
        const raf2 = requestAnimationFrame(() => {
          setIsAnimatingIn(true);
        });
        return () => cancelAnimationFrame(raf2);
      });
      return () => cancelAnimationFrame(raf1);
    } else {
      setIsAnimatingIn(false);
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
      closeTimerRef.current = setTimeout(() => {
        setIsMounted(false);
      }, 200);
    }
  }, [propNode]);

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
    };
  }, []);

  // Dismiss on Escape key
  useEffect(() => {
    if (!isAnimatingIn) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAnimatingIn, handleClose]);

  const node = propNode || cachedNode;

  if (!isMounted || !node) {
    return null;
  }

  const isStructureNode =
    node.type === 'structure' ||
    node.data?.type === 'structure' ||
    !!node.data?.workspace_path ||
    !!node.workspace_path;

  // Script node attributes
  const scriptName = node.data?.label || node.script_name || 'Step';
  const parameters = node.parameters || node.data?.parameters || {};
  const task = taskById.get(node.data?.task_id ?? node.task_id);
  const wiredInputs = Object.entries(
    (node.data?.inputs ?? node.inputs ?? {}) as InputFiles
  );
  const logs = node.logs || node.data?.logs || '';
  const hasPlots = !!task?.outputs.some(
    (output) => output.name === PLOTS_OUTPUT
  );
  // The tab left open on another step may not exist on this one.
  const tabIsGone =
    (scriptTab === 'plots' && !hasPlots) || (scriptTab === 'ai' && !ai.kind);
  const openTab = tabIsGone ? 'params' : scriptTab;
  const fallbackDefaults =
    defaultParameters ||
    node.default_parameters ||
    node.data?.default_parameters ||
    node.data?.originalData?.default_parameters ||
    {};
  const hasDefaults = fallbackDefaults && Object.keys(fallbackDefaults).length > 0;

  // Structure node attributes
  const structData = node.data || node;
  const filename = structData.filename || 'Input file';
  const rawContent = structData.raw_content || '';
  const lineCount =
    structData.line_count || (rawContent ? rawContent.split(/\r?\n/).filter(Boolean).length : 0);
  const sizeKb = structData.size_bytes ? (structData.size_bytes / 1024).toFixed(1) : '0.0';

  // Every setting back where the step started: the task's defaults as
  // the catalog has them now, under the values it was created with (a
  // prebuilt workflow's own).
  const canReset = !!task || hasDefaults;
  const handleResetDefaults = () => {
    if (!onUpdateParameters || !canReset) return;
    const taskDefaults = task ? defaultParameterValues(task) : {};
    onUpdateParameters({ ...taskDefaults, ...fallbackDefaults });
  };

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/60 backdrop-blur-xs transition-opacity duration-200 ${
        isAnimatingIn ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          handleClose();
        }
      }}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        className={`w-full max-w-3xl lg:max-w-4xl bg-white rounded-xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden transition-all duration-200 ease-out transform ${
          isAnimatingIn ? 'scale-100 opacity-100 translate-y-0' : 'scale-95 opacity-0 translate-y-2'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={`${TILE_CLASS} ${
                isStructureNode ? FILE_TILE_CLASS : STEP_TILE_CLASS
              }`}
            >
              <FileText className="w-4.5 h-4.5" />
            </div>
            <div className="flex flex-col min-w-0">
              <h3 className="font-bold text-slate-900 text-base truncate">
                {isStructureNode ? filename : scriptName}
              </h3>
              {isStructureNode && rawContent && (
                <span className="text-xs text-slate-500 mt-0.5 truncate">
                  {lineCount} lines · {sizeKb} KB
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition-colors cursor-pointer shrink-0"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation (Script Nodes only) */}
        {!isStructureNode && (
          <div className="flex border-b border-slate-200 bg-slate-50/70 px-6 gap-6 text-xs shrink-0">
            <TabButton
              label="Parameters"
              isActive={openTab === 'params'}
              onClick={() => setScriptTab('params')}
            />
            <TabButton
              label="Logs"
              isActive={openTab === 'logs'}
              onClick={() => setScriptTab('logs')}
            />
            {hasPlots && (
              <TabButton
                label="Plots"
                isActive={openTab === 'plots'}
                onClick={() => setScriptTab('plots')}
              />
            )}
            <TabButton
              label="Artifacts"
              isActive={openTab === 'artifacts'}
              onClick={() => setScriptTab('artifacts')}
            />
            {ai.kind && (
              <TabButton
                label="AI"
                isActive={openTab === 'ai'}
                onClick={() => setScriptTab('ai')}
              />
            )}
          </div>
        )}

        {/* Modal Body: Constant height so tab size never jumps or resizes */}
        <div className={MODAL_BODY}>
          {/* Structure Node Body */}
          {isStructureNode && (
            <div className="h-full flex flex-col gap-3">
              {/* Light background: never black */}
              <div className="flex-1 min-h-0 bg-slate-50 border border-slate-200 rounded-lg p-4 overflow-auto">
                <pre className="font-mono text-xs text-slate-800 whitespace-pre leading-relaxed select-text font-normal">
                  {rawContent || 'No file yet.'}
                </pre>
              </div>
            </div>
          )}

          {/* Script Node Body */}
          {!isStructureNode && (
            <div className="h-full flex flex-col">
              {/* Parameters Tab: with scrollbar when content gets longer */}
              {openTab === 'params' && (
                <div className="h-full overflow-y-auto pr-2 flex flex-col gap-4">
                  {wiredInputs.map(([port, files]) => (
                    <div key={port} className={WIRED_ROW_CLASS}>
                      <span className="text-slate-800 font-medium truncate">
                        {port}: {files.join(', ')}
                      </span>
                    </div>
                  ))}

                  <div className="flex-1">
                    <ParameterForm
                      parameters={parameters}
                      specs={task?.parameters}
                      onChange={(newParams) => {
                        if (onUpdateParameters) {
                          onUpdateParameters(newParams);
                        }
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Logs Tab: Light background, never black */}
              {openTab === 'logs' && (
                <div className="h-full flex flex-col">
                  <div className="flex-1 min-h-0 bg-slate-50 border border-slate-200 rounded-lg p-4 font-mono text-xs text-slate-800 overflow-auto leading-relaxed whitespace-pre-wrap select-text">
                    {logs || (
                      <span className="text-slate-400">No output yet.</span>
                    )}
                  </div>
                </div>
              )}

              {openTab === 'plots' && (
                <JobPlots jobId={jobId} status={stepStatus} />
              )}

              {/* Artifacts Tab */}
              {openTab === 'artifacts' && (
                <JobArtifacts jobId={jobId} status={stepStatus} />
              )}

              {openTab === 'ai' && jobId && (
                <Suspense fallback={AI_TAB_LOADING}>
                  <JobAiReview
                    jobId={jobId}
                    aiKey={aiKey}
                    ai={ai}
                  />
                </Suspense>
              )}
            </div>
          )}
        </div>

        {/* Footer Action Bar */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2">
            {onDelete && (
              <button
                type="button"
                onClick={() => {
                  handleClose();
                  onDelete();
                }}
                className="py-1.5 px-3 border border-red-200 bg-white hover:bg-red-50 text-red-600 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete</span>
              </button>
            )}

            {!isStructureNode && canReset && (
              <button
                type="button"
                onClick={handleResetDefaults}
                title="Reset parameters to defaults"
                className={FOOTER_BUTTON}
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                <span>Reset</span>
              </button>
            )}

            {isStructureNode && (
              <>
                <input
                  type="file"
                  id="modal-replace-file"
                  className="hidden"
                  accept={INPUT_FILE_TYPES}
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      const file = e.target.files[0];
                      if (structData.onFileUpload) {
                        structData.onFileUpload(node.id, file);
                      }
                    }
                  }}
                />
                <label
                  htmlFor="modal-replace-file"
                  title="Replace the file"
                  className={FOOTER_BUTTON}
                >
                  <Upload className="w-3.5 h-3.5 text-slate-500" />
                  <span>Replace</span>
                </label>
                {rawContent && (
                  <button
                    type="button"
                    onClick={() =>
                      triggerFileDownload(rawContent, filename, 'text/plain')
                    }
                    className={FOOTER_BUTTON}
                  >
                    <Download className="w-3.5 h-3.5 text-slate-500" />
                    <span>Download</span>
                  </button>
                )}
              </>
            )}
          </div>

          <div className="flex items-center gap-2 min-w-0">
            {/* The AI tab has its own, and says the same about a key. */}
            {!isStructureNode && openTab !== 'ai' && (
              <AiStepButton
                aiKey={aiKey}
                ai={ai}
                onOpen={() => setScriptTab('ai')}
              />
            )}
            <RunFilesButton runId={runId ?? null} />
          </div>
        </div>
      </div>
    </div>
  );
}
