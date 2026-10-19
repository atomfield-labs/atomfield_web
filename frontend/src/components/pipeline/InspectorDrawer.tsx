import { useState, useEffect, useRef, useCallback } from 'react';
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
  defaultParameters
}: InspectorDrawerProps) {
  const [cachedNode, setCachedNode] = useState(propNode);
  const [isMounted, setIsMounted] = useState(!!propNode);
  const [isSlidingIn, setIsSlidingIn] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Tabs for script nodes
  const [scriptTab, setScriptTab] = useState<'params' | 'logs' | 'artifacts'>('params');
  const [isDownloading, setIsDownloading] = useState(false);

  const handleClose = useCallback(() => {
    setIsSlidingIn(false);
    onClose();
  }, [onClose]);

  // Synchronize propNode with local display and slide animation
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
          setIsSlidingIn(true);
        });
        return () => cancelAnimationFrame(raf2);
      });
      return () => cancelAnimationFrame(raf1);
    } else {
      setIsSlidingIn(false);
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
      closeTimerRef.current = setTimeout(() => {
        setIsMounted(false);
      }, 300);
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

  // Dismiss on click anywhere outside the inspector
  useEffect(() => {
    if (!isSlidingIn) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;

      if (drawerRef.current && drawerRef.current.contains(target)) {
        return;
      }

      handleClose();
    };

    window.addEventListener('pointerdown', handlePointerDown, true);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown, true);
    };
  }, [isSlidingIn, handleClose]);

  // Dismiss on Escape key
  useEffect(() => {
    if (!isSlidingIn) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isSlidingIn, handleClose]);

  const node = propNode || cachedNode;

  if (!isMounted || !node) {
    return null;
  }

  const isStructureNode = node.type === 'structure' || node.data?.type === 'structure' || !!node.data?.workspace_path || !!node.workspace_path;

  // Script node attributes
  const scriptName = node.script_name || node.data?.label || 'Unknown Script';
  const parameters = node.parameters || node.data?.parameters || {};
  const logs = node.logs || node.data?.logs || '';
  const status = node.status || node.data?.status || 'Draft';
  const fallbackDefaults = defaultParameters || node.default_parameters || node.data?.default_parameters || node.data?.originalData?.default_parameters || {};
  const hasDefaults = fallbackDefaults && Object.keys(fallbackDefaults).length > 0;

  // Structure node attributes
  const structData = node.data || node;
  const filename = structData.filename || 'Structure Input';
  const format = (structData.format || (filename.includes('.') ? filename.split('.').pop()?.toUpperCase() : 'XYZ') || 'XYZ').toUpperCase();
  const rawContent = structData.raw_content || '';
  const lineCount = structData.line_count || (rawContent ? rawContent.split(/\r?\n/).filter(Boolean).length : 0);
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
      const sessionId = node.pipeline_id || node.data?.pipeline_id || node.session_id || node.parameters?.pipeline_id || '';
      const blob = await jobsService.downloadJobArtifacts(jobId, sessionId);
      const cleanName = (isStructureNode ? (filename || 'structure') : (scriptName || 'workspace')).replace(/[^a-zA-Z0-9_-]/g, '_');
      triggerFileDownload(blob, `artifacts_${cleanName}.zip`, 'application/zip');
    } catch (err) {
      console.error("Failed to download artifacts:", err);
      alert("Artifacts are not available yet.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div 
      ref={drawerRef}
      data-inspector-drawer="true"
      className={`absolute top-0 right-0 bottom-0 w-[420px] bg-white border-l border-slate-200 shadow-2xl flex flex-col z-30 transition-transform duration-300 ease-in-out ${
        isSlidingIn ? 'translate-x-0' : 'translate-x-full pointer-events-none'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50">
        <div className="flex items-center gap-2.5 truncate pr-2">
          {isStructureNode && (
            <div className="w-8 h-8 rounded-lg bg-orange-50 text-orange-600 border border-orange-200/70 flex items-center justify-center shrink-0 shadow-2xs">
              <CH4Icon size={18} className="w-4.5 h-4.5" />
            </div>
          )}
          <div className="flex flex-col truncate">
            <h3 className="font-bold text-slate-900 truncate text-sm">
              {isStructureNode ? filename : scriptName}
            </h3>
            <span className="text-[10px] font-mono text-slate-400">
              {isStructureNode
                ? 'Molecular Structure Asset'
                : `ID: ${node.id?.substring(0, 12)} • ${status}${node.data?.execution_time_seconds ? ` • ${node.data.execution_time_seconds}s` : ''}`}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button 
            onClick={handleClose} 
            className="p-1 hover:bg-slate-200 rounded text-slate-500 font-bold leading-none text-lg cursor-pointer"
          >
            &times;
          </button>
        </div>
      </div>

      {/* Navigation Tabs (Script nodes only) */}
      {!isStructureNode && (
        <div className="flex border-b border-slate-200 bg-slate-50">
          <button 
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider ${
              scriptTab === 'params' ? 'text-orange-600 border-b-2 border-orange-600 bg-white' : 'text-slate-500'
            }`}
            onClick={() => setScriptTab('params')}
          >
            Params
          </button>
          <button 
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider ${
              scriptTab === 'logs' ? 'text-orange-600 border-b-2 border-orange-600 bg-white' : 'text-slate-500'
            }`}
            onClick={() => setScriptTab('logs')}
          >
            Logs
          </button>
          <button 
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider ${
              scriptTab === 'artifacts' ? 'text-orange-600 border-b-2 border-orange-600 bg-white' : 'text-slate-500'
            }`}
            onClick={() => setScriptTab('artifacts')}
          >
            Artifacts
          </button>
        </div>
      )}

      {/* Main Drawer Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* STRUCTURE NODE BODY: White Paged Document */}
        {isStructureNode && (
          <div className="h-full flex flex-col gap-3">
            {/* Document Header & Actions */}
            <div className="flex justify-between items-center pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded font-mono text-[10px] font-bold">
                  .{format}
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {lineCount} lines • {sizeKb} KB
                </span>
              </div>
              <div>
                {rawContent && (
                  <button
                    onClick={() => {
                      triggerFileDownload(rawContent, filename || `structure.${format.toLowerCase()}`, 'text/plain');
                    }}
                    className="px-2.5 py-1 bg-white border border-slate-200 hover:border-slate-400 text-slate-600 rounded text-[11px] font-medium transition-all shadow-2xs hover:bg-slate-50"
                  >
                    Download
                  </button>
                )}
              </div>
            </div>

            {/* White Paged Document */}
            <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-xl shadow-xs p-4 overflow-auto">
              <pre className="font-mono text-xs text-slate-800 whitespace-pre leading-relaxed select-text font-normal">
                {rawContent || '# No file content available'}
              </pre>
            </div>
          </div>
        )}

        {/* SCRIPT NODE BODY */}
        {!isStructureNode && (
          <>
            {scriptTab === 'params' && (
              <div>
                {/* Structure Connection Banner if input is wired */}
                {parameters.input && (
                  <div className="mb-4 p-2.5 bg-slate-100 border border-slate-200 rounded-xl flex items-center justify-between text-xs font-mono">
                    <span className="text-slate-800 font-bold truncate">
                      Input: {parameters.input.replace('/workspace/', '')}
                    </span>
                    <span className="px-1.5 py-0.5 bg-slate-200 text-slate-700 text-[10px] font-bold rounded shrink-0">
                      BOUND
                    </span>
                  </div>
                )}

                <YamlParamEditor
                  parameters={parameters}
                  onChange={(newParams) => {
                    if (onUpdateParameters) {
                      onUpdateParameters(newParams);
                    }
                  }}
                />
              </div>
            )}
            
            {scriptTab === 'logs' && (
              <div className="h-full bg-white border border-slate-200 rounded-lg p-3 font-mono text-xs text-slate-800 overflow-y-auto whitespace-pre-wrap leading-relaxed select-text">
                {logs || (
                  <span className="text-slate-400 italic">Waiting for execution to begin...</span>
                )}
              </div>
            )}

            {scriptTab === 'artifacts' && (
              <div className="h-full flex flex-col gap-3">
                {((node.artifacts && Array.isArray(node.artifacts) && node.artifacts.length > 0) || (node.data?.artifacts && Array.isArray(node.data?.artifacts) && node.data.artifacts.length > 0)) ? (
                  <div className="flex flex-col gap-2">
                    {(node.artifacts || node.data?.artifacts || []).map((art: any, idx: number) => (
                      <div key={idx} className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 flex items-center justify-between">
                        <span className="truncate">{typeof art === 'string' ? art : art.name || art.path}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="h-32 flex flex-col items-center justify-center text-xs text-slate-400 bg-slate-50 border border-dashed border-slate-200 rounded-lg p-4 text-center">
                    <svg className="w-8 h-8 text-slate-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>No artifacts generated yet</span>
                    <span className="text-[10px] text-slate-400 mt-0.5">Outputs will appear here after execution</span>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      {(onDelete || (!isStructureNode && hasDefaults) || isStructureNode) && (
        <div className="p-3 border-t border-slate-200 bg-slate-50 flex items-center gap-2">
          {onDelete && (
            <button
              onClick={() => {
                handleClose();
                onDelete();
              }}
              className="flex-1 py-2 px-3 border border-red-200 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-1.5 shadow-sm cursor-pointer"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete Node from Graph
            </button>
          )}

          {/* Download Artifacts as Compressed File (.zip) */}
          <button
            type="button"
            onClick={handleDownloadArtifacts}
            disabled={isDownloading}
            title="Download artifacts as compressed ZIP"
            className="py-2 px-2.5 border border-slate-200 bg-white hover:bg-orange-50 hover:border-orange-200 text-slate-400 hover:text-orange-600 rounded-lg transition-colors shadow-sm flex items-center justify-center shrink-0 disabled:opacity-50"
          >
            {isDownloading ? (
              <span className="w-4 h-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            )}
          </button>
          {isStructureNode && (
            <>
              <input
                type="file"
                id="drawer-replace-file-footer"
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
                htmlFor="drawer-replace-file-footer"
                title="Replace structure file"
                className="cursor-pointer py-2 px-2.5 border border-slate-200 bg-white hover:bg-orange-50 hover:border-orange-200 text-slate-400 hover:text-orange-600 rounded-lg transition-colors shadow-sm flex items-center justify-center shrink-0"
              >
                <svg className="w-4 h-4 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </label>
            </>
          )}
          {!isStructureNode && hasDefaults && (
            <button
              type="button"
              onClick={handleResetDefaults}
              title="Reset parameters to defaults"
              className="py-2 px-2.5 border border-slate-200 bg-white hover:bg-orange-50 hover:border-orange-200 text-slate-400 hover:text-orange-600 rounded-lg transition-colors shadow-sm flex items-center justify-center shrink-0"
            >
              <svg className="w-4 h-4 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
