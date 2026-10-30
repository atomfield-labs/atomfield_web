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
import { useSessionDraft } from '../../hooks/useSessionDraft';
import { useRunEvents } from '../../hooks/useRunEvents';
import {
  loadTaskDefinitions,
  useTaskDefinitions,
} from '../../hooks/useTaskDefinitions';
import { buildPipelineSubmitPayload } from '../../utils/pipelinePayload';
import { runProgress, type RunProgress } from '../../utils/jobStatus';
import { templateToBlueprint } from '../../utils/templates';
import type {
  PipelineTemplate,
  SessionMetadata,
  TaskDefinition,
} from '../../types/api';

export type { SessionMetadata };

interface PipelineEditorProps {
  sessionId?: string;
}

// A new pipeline: #pipeline/new, or #pipeline/new/<template id> to
// start from one of the catalog's templates.
const NEW_SESSION = 'new';
const FROM_TEMPLATE = 'new/';
// Steps that run as jobs: plain steps, and a sweep's copies.
const STEP_TYPES = new Set(['default', 'branchCircle']);
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
  // A template to open with, when arriving by a template's link.
  const [templateId] = useState(() => templateIdOf(sessionId));
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [isDeploying, setIsDeploying] = useState(false);
  const [progress, setProgress] = useState<RunProgress>(NOT_RUN);
  const [activeJobMap, setActiveJobMap] = useState<Record<string, string>>({});
  const [activePipelineId, setActivePipelineId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  // Where to run; null means the shared AtomField server.
  const [targetId, setTargetId] = useState<string | null>(null);
  // Which input of each task a connected structure file belongs to.
  const { taskById } = useTaskDefinitions();

  const currentGraphRef = useRef<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const deleteNodeRef = useRef<((nodeId: string) => void) | null>(null);
  const updateNodeParamsRef = useRef<((nodeId: string, newParams: Record<string, any>) => void) | null>(null);
  const updateNodeExecutionRef = useRef<((nodeId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => void) | null>(null);
  const replicateNodeRef = useRef<((nodeId: string, count: number) => void) | null>(null);

  const { blueprint, setBlueprint } = useBlueprint(activeSessionId);
  const {
    saveStatus,
    setSaveStatus,
    autosaveGraph,
    markSessionRunning,
    title,
    nameSession,
  } = useSessionDraft(activeSessionId);

  // Route hash sync
  useEffect(() => {
    if (sessionId && !isNewSession(sessionId)) {
      setActiveSessionId(sessionId);
    } else {
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
          if (parsed.run_id) setActiveRunId(parsed.run_id);
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
          matchingJobs.forEach((j) => {
            const nodeKey = j.parameters?.node || j.script_name;
            resolvedMap[nodeKey] = j.id;
          });
          // Follow the newest submission of this session.
          const newest = matchingJobs.reduce((a, b) =>
            a.created_at > b.created_at ? a : b
          );
          setActiveJobMap(resolvedMap);
          setActivePipelineId(activeSessionId);
          setActiveRunId(newest.run_id);
          localStorage.setItem(
            `atomfield_jobs_${activeSessionId}`,
            JSON.stringify({
              job_ids: resolvedMap,
              pipeline_id: activeSessionId,
              run_id: newest.run_id,
            })
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
    activePipelineId,
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

    setIsDeploying(true);
    setSaveStatus('saving');
    try {
      const response = await jobsService.submitPipeline(payload);
      if (response.job_ids) {
        // Cached at once, so a reload follows the same run.
        try {
          localStorage.setItem(
            `atomfield_jobs_${activeSessionId}`,
            JSON.stringify({
              job_ids: response.job_ids,
              pipeline_id: response.pipeline_id || activeSessionId,
              run_id: response.run_id,
            })
          );
        } catch (e) {
          console.error('Failed to cache job mapping', e);
        }

        setActiveJobMap(response.job_ids);
        setActiveRunId(response.run_id);
        if (response.pipeline_id) {
          setActivePipelineId(response.pipeline_id);
        }
        Object.entries(response.job_ids).forEach(([uiId, jobId]) => {
          if (updateNodeExecutionRef.current) {
            updateNodeExecutionRef.current(uiId, 'Pending', 'Waiting to start...', [], jobId);
          }
        });
      }
      markSessionRunning();
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
      localStorage.setItem(
        `atomfield_blueprint_${activeSessionId}`,
        JSON.stringify(loaded)
      );
      nameSession(template.title);
    },
    [activeSessionId, setBlueprint, nameSession]
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
          <LeftSidebar onLoadTemplate={handleLoadTemplate} />

          <div className="flex-1 h-full relative">
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
