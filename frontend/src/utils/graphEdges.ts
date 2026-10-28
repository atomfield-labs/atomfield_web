import type { Edge } from '@xyflow/react';
import type { BlueprintEdge } from '../types/api';

// Where an edge attaches when no handle was saved: a structure's main
// output, a task's right-hand output, a task's left-hand input.
const STRUCTURE_OUT = 'structure-out';
const TASK_OUT = 'source-right';
const TASK_IN = 'target-left';

export interface Connection {
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

/**
 * Point a connection the way data flows: a structure file always flows
 * into a task, whichever end the user dragged from. Null for a
 * connection that means nothing (structure to structure).
 */
export function orientConnection(
  connection: Connection,
  isStructure: (nodeId: string) => boolean
): Connection | null {
  const fromStructure = isStructure(connection.source);
  const intoStructure = isStructure(connection.target);
  if (fromStructure && intoStructure) return null;
  if (!intoStructure) return connection;
  return {
    source: connection.target,
    target: connection.source,
    sourceHandle: STRUCTURE_OUT,
    targetHandle: TASK_IN,
  };
}

/**
 * The canvas edge for a saved one: its saved handles, or the usual
 * ones for drafts saved without them, pointed the way data flows (so a
 * draft with a backwards structure link is repaired on load).
 */
export function restoreEdge(
  saved: BlueprintEdge,
  isStructure: (nodeId: string) => boolean
): Edge | null {
  const oriented = orientConnection(
    {
      source: saved.upstream_ui_id,
      target: saved.downstream_ui_id,
      sourceHandle: saved.source_handle,
      targetHandle: saved.target_handle,
    },
    isStructure
  );
  if (!oriented) return null;
  const defaultSource = isStructure(oriented.source) ? STRUCTURE_OUT : TASK_OUT;
  return {
    id: `e-${oriented.source}-${oriented.target}`,
    source: oriented.source,
    target: oriented.target,
    sourceHandle: oriented.sourceHandle || defaultSource,
    targetHandle: oriented.targetHandle || TASK_IN,
    type: 'removable',
    animated: true,
    style: { stroke: '#94a3b8', strokeWidth: 2 },
  };
}

/**
 * How an edge is saved in a draft: its ends and the handles it is
 * attached to, so it comes back exactly where it was.
 */
export function saveEdge(edge: Edge): BlueprintEdge {
  return {
    id: edge.id,
    upstream_ui_id: edge.source,
    downstream_ui_id: edge.target,
    source_handle: edge.sourceHandle ?? null,
    target_handle: edge.targetHandle ?? null,
  };
}
