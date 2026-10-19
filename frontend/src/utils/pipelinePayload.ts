import type { Node, Edge } from '@xyflow/react';
import type { PipelineSubmitRequest, PipelineSubmitFile } from '../types/api';

export interface PayloadBuildResult {
  isValid: boolean;
  errorMessage?: string;
  payload?: PipelineSubmitRequest;
}

/**
 * Builds and validates the DAG execution payload from the active ReactFlow graph.
 */
export function buildPipelineSubmitPayload(
  graph: { nodes: Node[]; edges: Edge[] },
  sessionId: string
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
      const scriptName =
        data.filename ||
        data.script_id ||
        (data.label?.endsWith('.py') ? data.label : `${data.label}.py`);

      return {
        ui_id: node.id,
        script_name: scriptName,
        parameters: data.parameters || {},
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
