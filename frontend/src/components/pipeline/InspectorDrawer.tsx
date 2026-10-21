import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Trash2, Download, RotateCcw, FileText, Upload } from 'lucide-react';
import { jobsService } from '../../api/services';
import { triggerFileDownload } from '../../utils/downloadHelper';
import YamlParamEditor from './YamlParamEditor';
import CH4Icon from '../icons/CH4Icon';

interface InspectorDrawerProps {
  node: any | null;
  onClose: () => void;
  onDelete?: () => void;
  onUpdateParameters?: (newParams: Record<string, any>) => void;
  defaultParameters?: Record<string, any>;
}

export default function InspectorDrawer({
  node: propNode,
  onClose,
  onDelete,
  onUpdateParameters,
  defaultParameters,
}: InspectorDrawerProps) {
  const [cachedNode, setCachedNode] = useState(propNode);
  const [isMounted, setIsMounted] = useState(!!propNode);
  const [isAnimatingIn, setIsAnimatingIn] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Tabs for script nodes: params | logs | artifacts
  const [scriptTab, setScriptTab] = useState<'params' | 'logs' | 'artifacts'>('params');
  const [isDownloading, setIsDownloading] = useState(false);

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
  const scriptName = node.script_name || node.data?.label || 'Unknown Script';
  const parameters = node.parameters || node.data?.parameters || {};
  const logs = node.logs || node.data?.logs || '';
  const fallbackDefaults =
    defaultParameters ||
    node.default_parameters ||
    node.data?.default_parameters ||
    node.data?.originalData?.default_parameters ||
    {};
  const hasDefaults = fallbackDefaults && Object.keys(fallbackDefaults).length > 0;

  // Structure node attributes
  const structData = node.data || node;
  const filename = structData.filename || 'Structure Input';
  const format = (
    structData.format ||
    (filename.includes('.') ? filename.split('.').pop()?.toUpperCase() : 'XYZ') ||
    'XYZ'
  ).toUpperCase();
  const rawContent = structData.raw_content || '';
  const lineCount =
    structData.line_count || (rawContent ? rawContent.split(/\r?\n/).filter(Boolean).length : 0);
  const sizeKb = structData.size_bytes ? (structData.size_bytes / 1024).toFixed(1) : '0.0';

  const handleResetDefaults = () => {
    if (onUpdateParameters && hasDefaults) {
      onUpdateParameters({ ...fallbackDefaults });
    }
  };

  const handleDownloadArtifacts = async () => {
    try {
      setIsDownloading(true);
      const jobId = node.job_id || node.data?.job_id || node.id || node.ui_id || '';
      const sessionId =
        node.pipeline_id ||
        node.data?.pipeline_id ||
        node.session_id ||
        node.parameters?.pipeline_id ||
        '';
      const blob = await jobsService.downloadJobArtifacts(jobId, sessionId);
      const cleanName = (isStructureNode ? filename || 'structure' : scriptName || 'workspace').replace(
        /[^a-zA-Z0-9_-]/g,
        '_'
      );
      triggerFileDownload(blob, `artifacts_${cleanName}.zip`, 'application/zip');
    } catch (err) {
      console.error('Failed to download artifacts:', err);
      alert('Artifacts are not available yet.');
    } finally {
      setIsDownloading(false);
    }
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
            {isStructureNode ? (
              <div className="w-9 h-9 rounded-lg bg-orange-50 text-orange-600 border border-orange-200 flex items-center justify-center shrink-0">
                <CH4Icon size={18} className="w-4.5 h-4.5" />
              </div>
            ) : (
              <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 border border-slate-200 flex items-center justify-center shrink-0">
                <FileText className="w-4.5 h-4.5 text-slate-600" />
              </div>
            )}
            <div className="flex flex-col min-w-0">
              <h3 className="font-bold text-slate-900 text-base truncate">
                {isStructureNode ? filename : scriptName}
              </h3>
              <span className="text-xs font-mono text-slate-500 mt-0.5 truncate">
                {isStructureNode
                  ? `.${format} Asset • ${lineCount} lines • ${sizeKb} KB`
                  : `ID: ${node.id?.substring(0, 14)}`}
              </span>
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
            <button
              type="button"
              className={`py-2.5 font-semibold transition-colors border-b-2 -mb-px cursor-pointer ${
                scriptTab === 'params'
                  ? 'text-orange-600 border-orange-500'
                  : 'text-slate-500 hover:text-slate-800 border-transparent'
              }`}
              onClick={() => setScriptTab('params')}
            >
              Parameters
            </button>
            <button
              type="button"
              className={`py-2.5 font-semibold transition-colors border-b-2 -mb-px cursor-pointer ${
                scriptTab === 'logs'
                  ? 'text-orange-600 border-orange-500'
                  : 'text-slate-500 hover:text-slate-800 border-transparent'
              }`}
              onClick={() => setScriptTab('logs')}
            >
              Live Logs
            </button>
            <button
              type="button"
              className={`py-2.5 font-semibold transition-colors border-b-2 -mb-px cursor-pointer ${
                scriptTab === 'artifacts'
                  ? 'text-orange-600 border-orange-500'
                  : 'text-slate-500 hover:text-slate-800 border-transparent'
              }`}
              onClick={() => setScriptTab('artifacts')}
            >
              Artifacts
            </button>
          </div>
        )}

        {/* Modal Body: Constant height so tab size never jumps or resizes */}
        <div className="h-[480px] p-6 overflow-hidden flex flex-col">
          {/* Structure Node Body */}
          {isStructureNode && (
            <div className="h-full flex flex-col gap-3">
              <div className="flex justify-between items-center text-xs shrink-0">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded font-mono text-[10px] font-bold">
                    .{format}
                  </span>
                  <span className="text-slate-500 font-mono text-xs">
                    {lineCount} lines • {sizeKb} KB
                  </span>
                </div>
                {rawContent && (
                  <button
                    type="button"
                    onClick={() => {
                      triggerFileDownload(
                        rawContent,
                        filename || `structure.${format.toLowerCase()}`,
                        'text/plain'
                      );
                    }}
                    className="px-3 py-1 bg-white border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 rounded text-xs font-medium transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
                  >
                    <Download className="w-3.5 h-3.5 text-slate-500" />
                    <span>Download file</span>
                  </button>
                )}
              </div>

              {/* Light background for coordinates: never black */}
              <div className="flex-1 min-h-0 bg-slate-50 border border-slate-200 rounded-lg p-4 overflow-auto">
                <pre className="font-mono text-xs text-slate-800 whitespace-pre leading-relaxed select-text font-normal">
                  {rawContent || '# No structure content available'}
                </pre>
              </div>
            </div>
          )}

          {/* Script Node Body */}
          {!isStructureNode && (
            <div className="h-full flex flex-col">
              {/* Parameters Tab: with scrollbar when content gets longer */}
              {scriptTab === 'params' && (
                <div className="h-full overflow-y-auto pr-2 flex flex-col gap-4">
                  {parameters.input && (
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between text-xs font-mono shrink-0">
                      <span className="text-slate-800 font-medium truncate">
                        Input structure: {parameters.input.replace('/workspace/', '')}
                      </span>
                      <span className="px-2 py-0.5 bg-orange-100 text-orange-700 border border-orange-200 text-[10px] font-bold rounded shrink-0">
                        WIRED
                      </span>
                    </div>
                  )}

                  <div className="flex-1">
                    <YamlParamEditor
                      parameters={parameters}
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
              {scriptTab === 'logs' && (
                <div className="h-full flex flex-col">
                  <div className="flex-1 min-h-0 bg-slate-50 border border-slate-200 rounded-lg p-4 font-mono text-xs text-slate-800 overflow-auto leading-relaxed whitespace-pre-wrap select-text">
                    {logs || (
                      <span className="text-slate-400 italic">
                        No log output recorded yet. Output will stream here during execution.
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Artifacts Tab */}
              {scriptTab === 'artifacts' && (
                <div className="h-full overflow-y-auto pr-2 flex flex-col gap-3">
                  {((node.artifacts && Array.isArray(node.artifacts) && node.artifacts.length > 0) ||
                    (node.data?.artifacts &&
                      Array.isArray(node.data?.artifacts) &&
                      node.data.artifacts.length > 0)) ? (
                    <div className="flex flex-col gap-2">
                      {(node.artifacts || node.data?.artifacts || []).map((art: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 flex items-center justify-between"
                        >
                          <span className="truncate">
                            {typeof art === 'string' ? art : art.name || art.path}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-xs text-slate-400 bg-slate-50/50 border border-dashed border-slate-200 rounded-lg p-6 text-center">
                      <FileText className="w-8 h-8 text-slate-300 mb-2" />
                      <span className="font-semibold text-slate-600">No artifacts generated yet</span>
                      <span className="text-slate-400 text-[11px] mt-0.5">
                        Generated files and results will appear here after task completion.
                      </span>
                    </div>
                  )}
                </div>
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
                <span>Delete Node</span>
              </button>
            )}

            {!isStructureNode && hasDefaults && (
              <button
                type="button"
                onClick={handleResetDefaults}
                title="Reset parameters to defaults"
                className="py-1.5 px-3 border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-2xs"
              >
                <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                <span>Reset Defaults</span>
              </button>
            )}

            {isStructureNode && (
              <>
                <input
                  type="file"
                  id="modal-replace-file"
                  className="hidden"
                  accept=".xyz,.cif,.sdf,.mol,.pdb"
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
                  title="Replace structure file"
                  className="cursor-pointer py-1.5 px-3 border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 shadow-2xs"
                >
                  <Upload className="w-3.5 h-3.5 text-slate-500" />
                  <span>Replace File</span>
                </label>
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownloadArtifacts}
              disabled={isDownloading}
              title="Download artifacts as compressed ZIP"
              className="py-1.5 px-3 border border-slate-200 bg-white hover:bg-orange-50 hover:border-orange-200 text-slate-700 hover:text-orange-600 text-xs font-semibold rounded-lg transition-colors shadow-2xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {isDownloading ? (
                <span className="w-3.5 h-3.5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5 text-orange-500" />
              )}
              <span>Download ZIP</span>
            </button>

            <button
              type="button"
              onClick={handleClose}
              className="py-1.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg transition-colors cursor-pointer shadow-2xs"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
