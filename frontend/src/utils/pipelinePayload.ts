import { currentParameters, inputPortForFile } from './taskCatalog';
import type { Node, Edge } from '@xyflow/react';
import type {
  InputFiles,
  PipelineSubmitRequest,
  PipelineSubmitFile,
  TaskDefinition,
} from '../types/api';

export interface PayloadBuildResult {
  isValid: boolean;
  errorMessage?: string;
  payload?: PipelineSubmitRequest;
}

/**
 * The files a task reads from the structure nodes connected to it:
 * each file goes to the task's input that accepts its type. Worked out
 * when deploying, so it does not matter whether the file was uploaded
 * before or after the nodes were connected.
 */
function connectedStructureInputs(
  nodeId: string,
  graph: { nodes: Node[]; edges: Edge[] },
  task: TaskDefinition | undefined
): InputFiles {
  const inputs: InputFiles = {};
  if (!task) return inputs;
  for (const edge of graph.edges || []) {
    if (edge.target !== nodeId) continue;
    const source = (graph.nodes || []).find((node) => node.id === edge.source);
    const filename = (source?.data as any)?.filename;
    if (source?.type !== 'structure' || !filename) continue;
    const port = inputPortForFile(task, filename);
    if (port) inputs[port] = [...(inputs[port] ?? []), filename];
  }
  return inputs;
}

/**
 * Builds and validates the DAG execution payload from the active ReactFlow graph.
 */
export function buildPipelineSubmitPayload(
  graph: { nodes: Node[]; edges: Edge[] },
  sessionId: string,
  taskById: Map<string, TaskDefinition>
): PayloadBuildResult {
  const executableNodes = (graph.nodes || []).filter(
    (node) => node.type !== 'structure' && node.type !== 'branchExpander' && node.type !== 'branchDots'
  );

  if (executableNodes.length === 0) {
    return {
      isValid: false,
      errorMessage: 'Please drag and drop at least one script onto the canvas before deploying.',
    };
  }

  const executableNodeIds = new Set(executableNodes.map((node) => node.id));
  const executableEdges = (graph.edges || []).filter(
    (edge) => executableNodeIds.has(edge.source) && executableNodeIds.has(edge.target)
  );

  const structureFiles: PipelineSubmitFile[] = (graph.nodes || [])
    .filter(
      (node) =>
        node.type === 'structure' &&
        (node.data as any)?.filename &&
        (node.data as any)?.raw_content
    )
    .map((node) => {
      const data = node.data as any;
      return {
        filename: data.filename,
        content: data.raw_content,
      };
    });

  const payload: PipelineSubmitRequest = {
    session_id: sessionId,
    nodes: executableNodes.map((node) => {
      const data = node.data as any;
      // task_id is set when a catalog task is dropped; the rest are
      // fallbacks for drafts saved before the catalog existed.
      const taskId =
        data.task_id || data.filename || data.script_id || data.label;

      const task = taskById.get(taskId);
      const connected = connectedStructureInputs(node.id, graph, task);
      return {
        ui_id: node.id,
        script_name: taskId,
        parameters: currentParameters(task, data.parameters || {}),
        inputs: { ...(data.inputs || {}), ...connected },
      };
    }),
    edges: executableEdges.map((edge) => ({
      upstream_ui_id: edge.source,
      downstream_ui_id: edge.target,
    })),
    files: structureFiles,
  };

  return { isValid: true, payload };
}
