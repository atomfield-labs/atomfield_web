import { useState, useEffect, useRef, useCallback } from 'react';
import { ReactFlowProvider, type Node, type Edge } from '@xyflow/react';
import LeftSidebar from './LeftSidebar';
import GraphCanvas from './GraphCanvas';
import InspectorDrawer from './InspectorDrawer';
import EditorHeader from './EditorHeader';
import { describeError } from '../../api/client';
import { jobsService } from '../../api/services';
import { useBlueprint } from '../../hooks/useBlueprint';
import { loadPipelineTemplates } from '../../hooks/usePipelineTemplates';
import { STEP_TYPES, useSessionDraft } from '../../hooks/useSessionDraft';
import { useRunEvents } from '../../hooks/useRunEvents';
import {
  loadTaskDefinitions,
  useTaskDefinitions,
} from '../../hooks/useTaskDefinitions';
import { buildPipelineSubmitPayload } from '../../utils/pipelinePayload';
import { runProgress, type RunProgress } from '../../utils/jobStatus';
import { templateToBlueprint } from '../../utils/templates';
import type { PipelineTemplate, TaskDefinition } from '../../types/api';

interface PipelineEditorProps {
  sessionId?: string;
}

interface StartedRun {
  sessionId: string;
  runId: string | null;
  jobIds: Record<string, string>;
}

const NO_JOBS: Record<string, string> = {};
const LOAD_FAILED = 'p-8 text-center text-sm text-red-600';

// A new pipeline: #pipeline/new, or #pipeline/new/<template id> to
// start from one of the catalog's templates.
const NEW_SESSION = 'new';
const FROM_TEMPLATE = 'new/';
const NOT_RUN: RunProgress = { phase: 'idle', done: 0, total: 0 };

function isNewSession(sessionId?: string): boolean {
  return (
    !sessionId ||
    sessionId === NEW_SESSION ||
    sessionId.startsWith(FROM_TEMPLATE)
  );
}

function templateIdOf(sessionId?: string): string | null {
  if (!sessionId?.startsWith(FROM_TEMPLATE)) return null;
  return sessionId.slice(FROM_TEMPLATE.length) || null;
}

function generateSessionId(sessionId?: string): string {
  if (sessionId && !isNewSession(sessionId)) return sessionId;
  return 'pipeline_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 6);
}

/**
 * The statuses of the steps that run as jobs.
 */
function stepStatuses(nodes: Node[]): (string | undefined)[] {
  return nodes
    .filter((node) => STEP_TYPES.has(node.type ?? 'default'))
    .map((node) => (node.data as { status?: string })?.status);
}

function sameProgress(left: RunProgress, right: RunProgress): boolean {
  return (
    left.phase === right.phase &&
    left.done === right.done &&
    left.total === right.total
  );
}

export default function PipelineEditor({ sessionId }: PipelineEditorProps) {
  const [activeSessionId, setActiveSessionId] = useState<string>(() => generateSessionId(sessionId));
  // A new pipeline has nothing saved to wait for.
  const [newSessionId] = useState(() =>
    isNewSession(sessionId) ? activeSessionId : null
  );
  // A template to open with, when arriving by a template's link.
  const [templateId] = useState(() => templateIdOf(sessionId));
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [isDeploying, setIsDeploying] = useState(false);
  const [progress, setProgress] = useState<RunProgress>(NOT_RUN);
  // A run started from this view; otherwise the newest one saved.
  const [startedRun, setStartedRun] = useState<StartedRun | null>(null);
  // Where to run; null until the picker finds somewhere.
  const [targetId, setTargetId] = useState<string | null>(null);
  // Which input of each task a connected structure file belongs to.
  const { taskById } = useTaskDefinitions();

  const currentGraphRef = useRef<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const deleteNodeRef = useRef<((nodeId: string) => void) | null>(null);
  const updateNodeParamsRef = useRef<((nodeId: string, newParams: Record<string, any>) => void) | null>(null);
  const updateNodeExecutionRef = useRef<((nodeId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => void) | null>(null);
  const replicateNodeRef = useRef<((nodeId: string, count: number) => void) | null>(null);

  const { saved, loadFailed, blueprint, setBlueprint } = useBlueprint(
    activeSessionId,
    activeSessionId === newSessionId
  );
  const {
    saveStatus,
    setSaveStatus,
    autosaveGraph,
    saveNow,
    title,
    nameSession,
  } = useSessionDraft(activeSessionId, saved);
  const started =
    startedRun?.sessionId === activeSessionId ? startedRun : null;
  const activeRunId = started?.runId ?? saved?.run_id ?? null;
  const activeJobMap = started?.jobIds ?? saved?.job_ids ?? NO_JOBS;

  // Route hash sync
  useEffect(() => {
    if (sessionId && !isNewSession(sessionId)) {
      setActiveSessionId(sessionId);
    } else {
      window.location.hash = `#pipeline/${activeSessionId}`;
    }
  }, [sessionId, activeSessionId]);

  // Live job updates
  const handleUpdateExecution = useCallback(
    (uiId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => {
      if (updateNodeExecutionRef.current) {
        updateNodeExecutionRef.current(uiId, status, logs, artifacts, jobId);
      }
    },
    []
  );

  useRunEvents({
    runId: activeRunId,
    activeJobMap,
    activePipelineId: activeSessionId,
    onUpdateExecution: handleUpdateExecution,
    onUpdateSelectedNode: setSelectedNode,
  });

  const handleGraphChange = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      currentGraphRef.current = graph;
      autosaveGraph(graph);
      const next = runProgress(stepStatuses(graph.nodes));
      setProgress((previous) =>
        sameProgress(previous, next) ? previous : next
      );
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
    const { isValid, errorMessage, payload } = buildPipelineSubmitPayload(
      currentGraphRef.current,
      activeSessionId,
      taskById
    );
    if (!isValid || !payload) {
      alert(errorMessage || 'Invalid pipeline configuration.');
      return;
    }
    payload.target_id = targetId;

    saveNow();
    setIsDeploying(true);
    setSaveStatus('saving');
    try {
      const response = await jobsService.submitPipeline(payload);
      if (response.job_ids) {
        setStartedRun({
          sessionId: activeSessionId,
          runId: response.run_id ?? null,
          jobIds: response.job_ids,
        });
        Object.entries(response.job_ids).forEach(([uiId, jobId]) => {
          if (updateNodeExecutionRef.current) {
            updateNodeExecutionRef.current(uiId, 'Pending', 'Waiting to start...', [], jobId);
          }
        });
      }
      setSaveStatus('deployed');
    } catch (err: any) {
      console.error('Pipeline deploy failed', err);
      const reason = describeError(err, err?.message || 'Unknown error');
      alert(`The pipeline did not start: ${reason}`);
      setSaveStatus('saved');
    } finally {
      setIsDeploying(false);
    }
  };

  // Stop every unfinished step; the statuses follow by themselves.
  const handleStop = async () => {
    if (!activeRunId) return;
    try {
      await jobsService.cancelRun(activeRunId);
    } catch (err) {
      alert(describeError(err, 'Could not stop the run.'));
    }
  };

  // A ready-made pipeline replaces the canvas, every setting shown, and
  // names the pipeline after itself.
  const loadTemplate = useCallback(
    (template: PipelineTemplate, tasks: Map<string, TaskDefinition>) => {
      const loaded = templateToBlueprint(template, tasks);
      setBlueprint(loaded);
      nameSession(template.title);
    },
    [setBlueprint, nameSession]
  );

  const handleLoadTemplate = useCallback(
    (template: PipelineTemplate) => loadTemplate(template, taskById),
    [loadTemplate, taskById]
  );

  // Arrived by a template's link: open it once the catalog is in.
  useEffect(() => {
    if (!templateId) return;
    void Promise.all([loadPipelineTemplates(), loadTaskDefinitions()]).then(
      ([templates, tasks]) => {
        const template = templates.find((item) => item.id === templateId);
        const byId = new Map(tasks.map((task) => [task.id, task]));
        if (template) loadTemplate(template, byId);
      }
    );
  }, [templateId, loadTemplate]);

  return (
    <div className="flex flex-col h-screen w-full bg-stone-50">
      <EditorHeader
        title={title}
        onRename={nameSession}
        saveStatus={saveStatus}
        progress={progress}
        isStarting={isDeploying}
        onRun={handleDeploy}
        onStop={handleStop}
        targetId={targetId}
        onTargetChange={setTargetId}
      />

      <div className="flex flex-1 overflow-hidden relative">
        <ReactFlowProvider>
          <LeftSidebar />

          <div className="flex-1 h-full relative">
            {loadFailed && saved === undefined && (
              <p role="alert" className={LOAD_FAILED}>
                Could not load this pipeline. Refresh to try again.
              </p>
            )}
            {saved !== undefined && (
              <GraphCanvas
                blueprint={blueprint}
                onNodeDoubleClick={(node) => setSelectedNode(node)}
                selectedNodeId={selectedNode?.id}
                isEditable={true}
                sessionId={activeSessionId}
                onRegisterDeleteHandler={(handler) => {
                  deleteNodeRef.current = handler;
                }}
                onRegisterUpdateParamsHandler={(handler) => {
                  updateNodeParamsRef.current = handler;
                }}
                onRegisterUpdateExecutionHandler={(handler) => {
                  updateNodeExecutionRef.current = handler;
                }}
                onRegisterReplicateHandler={(handler) => {
                  replicateNodeRef.current = handler;
                }}
                onGraphChange={handleGraphChange}
                onLoadTemplate={handleLoadTemplate}
                onNodesDelete={(deleted) => {
                  const selectedId = selectedNode?.id ?? selectedNode?.ui_id;
                  if (deleted.some((node) => node.id === selectedId)) {
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
            runId={activeRunId}
          />
        </ReactFlowProvider>
      </div>
    </div>
  );
}
