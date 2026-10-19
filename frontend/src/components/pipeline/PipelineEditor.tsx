import { useState, useEffect, useRef, useCallback } from 'react';
import { ReactFlowProvider, type Node, type Edge } from '@xyflow/react';
import LeftSidebar from './LeftSidebar';
import GraphCanvas from './GraphCanvas';
import InspectorDrawer from './InspectorDrawer';
import EditorHeader from './EditorHeader';
import { jobsService, pipelineService } from '../../api/services';
import { useQuota } from '../../hooks/useQuota';
import { useBlueprint } from '../../hooks/useBlueprint';
import { useSessionDraft, serializeGraphToBlueprint } from '../../hooks/useSessionDraft';
import { useJobPolling } from '../../hooks/useJobPolling';
import { buildPipelineSubmitPayload } from '../../utils/pipelinePayload';
import type { SessionMetadata } from '../../types/api';

export type { SessionMetadata };

interface PipelineEditorProps {
  sessionId?: string;
}

function generateSessionId(sessionId?: string): string {
  if (sessionId && sessionId !== 'new') return sessionId;
  return 'pipeline_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 6);
}

export default function PipelineEditor({ sessionId }: PipelineEditorProps) {
  const [activeSessionId, setActiveSessionId] = useState<string>(() => generateSessionId(sessionId));
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [isDeploying, setIsDeploying] = useState(false);
  const [activeJobMap, setActiveJobMap] = useState<Record<string, string>>({});
  const [activePipelineId, setActivePipelineId] = useState<string | null>(null);

  const currentGraphRef = useRef<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const deleteNodeRef = useRef<((nodeId: string) => void) | null>(null);
  const updateNodeParamsRef = useRef<((nodeId: string, newParams: Record<string, any>) => void) | null>(null);
  const updateNodeExecutionRef = useRef<((nodeId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => void) | null>(null);
  const replicateNodeRef = useRef<((nodeId: string, count: number) => void) | null>(null);

  // Custom Hooks
  const { quota, decrementQuota } = useQuota();
  const { blueprint, isLoading: isLoadingBlueprint, setBlueprint } = useBlueprint(activeSessionId);
  const { saveStatus, setSaveStatus, autosaveGraph, markSessionRunning } = useSessionDraft(activeSessionId);

  // Route hash sync
  useEffect(() => {
    if (sessionId && sessionId !== 'new') {
      setActiveSessionId(sessionId);
    } else if (!sessionId || sessionId === 'new') {
      window.location.hash = `#pipeline/${activeSessionId}`;
    }
  }, [sessionId, activeSessionId]);

  // Reconnect to active or existing jobs for this session
  useEffect(() => {
    let isCancelled = false;

    // 1. Try reading stored job map for this session
    const savedJobs = localStorage.getItem(`atomfield_jobs_${activeSessionId}`);
    let existingMap: Record<string, string> = {};
    if (savedJobs) {
      try {
        const parsed = JSON.parse(savedJobs);
        if (parsed.job_ids && Object.keys(parsed.job_ids).length > 0) {
          existingMap = parsed.job_ids;
          setActiveJobMap(parsed.job_ids);
          if (parsed.pipeline_id) setActivePipelineId(parsed.pipeline_id);
        }
      } catch (e) {
        console.error('Failed to parse saved jobs for session', e);
      }
    }

    // 2. Query cluster jobs for this session to ensure we connect to latest job execution
    jobsService
      .listJobs({ limit: 25 })
      .then(({ jobs }) => {
        if (isCancelled) return;
        const matchingJobs = jobs.filter(
          (j) => j.parameters?.pipeline_id === activeSessionId
        );

        if (matchingJobs.length > 0) {
          const resolvedMap: Record<string, string> = { ...existingMap };
          if (activeSessionId === 'nanoreactor') {
            resolvedMap['xtb_nanoreactor'] = matchingJobs[0].id;
          } else {
            matchingJobs.forEach((j) => {
              const nodeKey = j.parameters?.node || j.script_name;
              resolvedMap[nodeKey] = j.id;
            });
          }
          setActiveJobMap(resolvedMap);
          setActivePipelineId(activeSessionId);
          localStorage.setItem(
            `atomfield_jobs_${activeSessionId}`,
            JSON.stringify({ job_ids: resolvedMap, pipeline_id: activeSessionId })
          );
        }
      })
      .catch((err) => {
        console.error('Failed to query cluster jobs for session', err);
      });

    return () => {
      isCancelled = true;
    };
  }, [activeSessionId]);

  // Background execution polling
  const handleUpdateExecution = useCallback(
    (uiId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => {
      if (updateNodeExecutionRef.current) {
        updateNodeExecutionRef.current(uiId, status, logs, artifacts, jobId);
      }
    },
    []
  );

  useJobPolling({
    activeJobMap,
    activePipelineId,
    onUpdateExecution: handleUpdateExecution,
    onUpdateSelectedNode: setSelectedNode,
  });

  const handleGraphChange = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      currentGraphRef.current = graph;
      autosaveGraph(graph);
    },
    [autosaveGraph]
  );

  const handleDeleteNode = useCallback(() => {
    if (selectedNode && deleteNodeRef.current) {
      const nodeId = selectedNode.id || selectedNode.ui_id;
      deleteNodeRef.current(nodeId);
      setSelectedNode(null);
    }
  }, [selectedNode]);

  const handleUpdateParameters = useCallback(
    (newParams: Record<string, any>) => {
      if (!selectedNode) return;
      const nodeId = selectedNode.id || selectedNode.ui_id;
      if (updateNodeParamsRef.current) {
        updateNodeParamsRef.current(nodeId, newParams);
      }
      setSelectedNode((prev: any) => (prev ? { ...prev, parameters: newParams, data: { ...prev.data, parameters: newParams } } : null));
    },
    [selectedNode]
  );

  const handleDeploy = async () => {
    const isPrebuilt = activeSessionId === 'nanoreactor';
    const targetSessionId = isPrebuilt
      ? 'nanoreactor_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 6)
      : activeSessionId;

    const { isValid, errorMessage, payload } = buildPipelineSubmitPayload(
      currentGraphRef.current,
      targetSessionId
    );

    if (!isValid || !payload) {
      alert(errorMessage || 'Invalid pipeline configuration.');
      return;
    }

    setIsDeploying(true);
    setSaveStatus('saving');

    try {
      if (isPrebuilt) {
        // 1. Serialize and save blueprint under the newly spawned session
        try {
          const serializedBlueprint = serializeGraphToBlueprint(
            currentGraphRef.current.nodes,
            currentGraphRef.current.edges
          );
          localStorage.setItem(
            `atomfield_blueprint_${targetSessionId}`,
            JSON.stringify(serializedBlueprint)
          );
        } catch (e) {
          console.error('Failed to save blueprint for new prebuilt run', e);
        }

        // 2. Register new session entry in atomfield_sessions list
        try {
          const raw = localStorage.getItem('atomfield_sessions');
          const list: any[] = raw ? JSON.parse(raw) : [];
          const newSessionMeta: SessionMetadata = {
            id: targetSessionId,
            title: 'Nanoreactor Catalysis',
            status: 'Running',
            nodeCount: currentGraphRef.current.nodes.length,
            updatedAt: new Date().toISOString(),
          };
          list.unshift(newSessionMeta);
          localStorage.setItem('atomfield_sessions', JSON.stringify(list));
        } catch (e) {
          console.error('Failed to register session metadata for prebuilt run', e);
        }

        // 3. Switch activeSessionId and route hash to the newly created run session
        setActiveSessionId(targetSessionId);
        window.location.hash = `#pipeline/${targetSessionId}`;
      }

      const response = await jobsService.submitPipeline(payload);

      if (response.job_ids) {
        setActiveJobMap(response.job_ids);
        if (response.pipeline_id) {
          setActivePipelineId(response.pipeline_id);
        }
        try {
          localStorage.setItem(
            `atomfield_jobs_${targetSessionId}`,
            JSON.stringify({
              job_ids: response.job_ids,
              pipeline_id: response.pipeline_id || targetSessionId,
            })
          );
        } catch (e) {
          console.error('Failed to cache job mapping', e);
        }
        Object.entries(response.job_ids).forEach(([uiId, jobId]) => {
          if (updateNodeExecutionRef.current) {
            updateNodeExecutionRef.current(uiId, 'Running', 'Job queued in cluster...', [], jobId);
          }
        });
      }

      if (!isPrebuilt) {
        markSessionRunning();
      }
      setSaveStatus('deployed');
      decrementQuota();

      alert(
        `Pipeline launched successfully.\n\nSubmitted ${response.total_nodes} job(s) (${response.roots_started} root job(s) running in cluster).\nSession is now running with live tracking in Sessions.`
      );
    } catch (err: any) {
      console.error('Pipeline deploy failed', err);
      alert(`Pipeline deployment failed: ${err.response?.data?.detail || err.message || 'Unknown error'}`);
      setSaveStatus('saved');
    } finally {
      setIsDeploying(false);
    }
  };

  const handleLoadFlashWorkflow = useCallback(async () => {
    try {
      const flashBp = await pipelineService.getNanoreactorBlueprint();
      setBlueprint(flashBp);
      localStorage.setItem(
        `atomfield_blueprint_${activeSessionId}`,
        JSON.stringify(flashBp)
      );
    } catch (e) {
      console.error('Failed to load flash nanoreactor workflow', e);
    }
  }, [activeSessionId, setBlueprint]);

  const handleLoadModularWorkflow = useCallback(async () => {
    try {
      const modularBp = await pipelineService.getModularNanoreactorBlueprint();
      setBlueprint(modularBp);
      localStorage.setItem(
        `atomfield_blueprint_${activeSessionId}`,
        JSON.stringify(modularBp)
      );
    } catch (e) {
      console.error('Failed to load modular nanoreactor workflow', e);
    }
  }, [activeSessionId, setBlueprint]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50">
      <EditorHeader
        activeSessionId={activeSessionId}
        saveStatus={saveStatus}
        quota={quota}
        isDeploying={isDeploying}
        onDeploy={handleDeploy}
      />

      <div className="flex flex-1 overflow-hidden relative">
        <ReactFlowProvider>
          <LeftSidebar
            onLoadModularWorkflow={handleLoadModularWorkflow}
            onLoadFlashWorkflow={handleLoadFlashWorkflow}
          />


          <div className="flex-1 h-full relative">
            {isLoadingBlueprint ? (
              <div className="absolute inset-0 flex items-center justify-center text-slate-400 font-bold">
                Loading topology...
              </div>
            ) : (
              <GraphCanvas
                blueprint={blueprint}
                onNodeDoubleClick={(node) => setSelectedNode(node)}
                selectedNodeId={selectedNode?.id}
                isEditable={true}
                sessionId={activeSessionId}
                onRegisterDeleteHandler={(handler) => { deleteNodeRef.current = handler; }}
                onRegisterUpdateParamsHandler={(handler) => { updateNodeParamsRef.current = handler; }}
                onRegisterUpdateExecutionHandler={(handler) => { updateNodeExecutionRef.current = handler; }}
                onRegisterReplicateHandler={(handler) => { replicateNodeRef.current = handler; }}
                onGraphChange={handleGraphChange}
                onNodesDelete={(deleted) => {
                  if (selectedNode && deleted.some((d) => d.id === selectedNode.id || d.id === selectedNode.ui_id)) {
                    setSelectedNode(null);
                  }
                }}
              />
            )}
          </div>

          <InspectorDrawer
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onDelete={handleDeleteNode}
            onUpdateParameters={handleUpdateParameters}
          />
        </ReactFlowProvider>
      </div>
    </div>
  );
}
