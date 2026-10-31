import { useState, useEffect, useCallback, useRef } from 'react';
import type { Node, Edge } from '@xyflow/react';
import { sessionsService } from '../api/services';
import type {
  BlueprintEdge,
  BlueprintNode,
  PipelineBlueprint,
  SaveStatus,
  SessionDetail,
  SessionSave,
} from '../types/api';
import { saveEdge } from '../utils/graphEdges';

export const UNTITLED = 'Untitled pipeline';
// Steps that run as jobs: plain steps, and a sweep's copies.
export const STEP_TYPES = new Set(['default', 'branchCircle']);
// A moment after the last change, so dragging is one save, not hundreds.
const SAVE_AFTER_MS = 1000;

export function serializeGraphToBlueprint(nodes: Node[], edges: Edge[]): { nodes: BlueprintNode[]; edges: BlueprintEdge[] } {
  return {
    nodes: nodes
      .filter((node) => node.type !== 'branchExpander' && node.type !== 'branchDots')
      .map((node) => {
      const data = node.data as any;
      if (node.type === 'structure') {
        return {
          ui_id: node.id,
          id: node.id,
          type: 'structure',
          filename: data.filename,
          workspace_path: data.workspace_path,
          atom_count: data.atom_count,
          formula: data.formula,
          elements: data.elements,
          atoms: data.atoms,
          comment: data.comment,
          bounding_box: data.bounding_box,
          raw_content: data.raw_content,
          position: node.position,
        };
      }
      return {
        ui_id: node.id,
        id: node.id,
        type: node.type || 'default',
        script_name:
          data.task_id || data.filename || data.script_id || data.label,
        task_id: data.task_id,
        inputs: data.inputs || {},
        label: data.label,
        status: data.status || 'Draft',
        parameters: data.parameters || {},
        default_parameters: data.default_parameters || {},
        position: node.position,
        originalData: data.originalData,
        index: data.index,
        branchGroupId: data.branchGroupId,
        branchCount: data.branchCount,
      };
    }),
    edges: edges.map(saveEdge),
  };
}

/**
 * What a save must keep of a draft: all of it but the steps' statuses,
 * which the server knows anyway. So a status changing is not an edit.
 */
function draftKey(blueprint: PipelineBlueprint): string {
  const nodes = blueprint.nodes.map((node) => ({ ...node, status: undefined }));
  return JSON.stringify({ nodes, edges: blueprint.edges });
}

const EMPTY_DRAFT = draftKey({ nodes: [], edges: [] });
// A saved draft is on its way onto the canvas; what first appears there
// is that draft, not an edit.
const AWAITING_CANVAS = 'awaiting canvas';
// The last save failed, so whatever comes next is worth saving.
const NOT_SAVED = 'not saved';

/**
 * How many steps a draft has: its input files don't count.
 */
function stepCount(blueprint: PipelineBlueprint): number {
  return blueprint.nodes.filter((node) => STEP_TYPES.has(node.type ?? ''))
    .length;
}

/**
 * Save a pipeline on the server as it changes: a moment after the last
 * change, and on leaving. Nothing is saved until something changes, so
 * opening a pipeline does not touch it and an empty one leaves no card.
 */
export function useSessionDraft(
  activeSessionId: string,
  saved: SessionDetail | null | undefined
) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  // A name given in this view; otherwise the name it was saved with.
  const [named, setNamed] = useState<{ id: string; title: string } | null>(
    null
  );
  const title =
    named?.id === activeSessionId ? named.title : saved?.title || UNTITLED;
  const lastDraft = useRef<{ id: string; key: string } | null>(null);
  const waiting = useRef<SessionSave | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // One save at a time, so they reach the server in order.
  const sending = useRef<Promise<void>>(Promise.resolve());

  const send = useCallback(
    (change: SessionSave) => {
      setSaveStatus('saving');
      sending.current = sending.current
        .then(() => sessionsService.save(activeSessionId, change))
        .then(
          () => setSaveStatus('saved'),
          (error) => {
            console.error('Save failed', error);
            lastDraft.current = { id: activeSessionId, key: NOT_SAVED };
            setSaveStatus('failed');
          }
        );
    },
    [activeSessionId]
  );

  const saveNow = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (waiting.current) send(waiting.current);
    waiting.current = null;
  }, [send]);

  // Whatever is waiting goes on leaving this pipeline.
  useEffect(() => saveNow, [saveNow]);

  const autosaveGraph = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      if (lastDraft.current?.id !== activeSessionId) {
        const hasDraft = (saved?.blueprint?.nodes?.length ?? 0) > 0;
        const key = hasDraft ? AWAITING_CANVAS : EMPTY_DRAFT;
        lastDraft.current = { id: activeSessionId, key };
      }
      const blueprint = serializeGraphToBlueprint(graph.nodes, graph.edges);
      const key = draftKey(blueprint);
      if (lastDraft.current.key === AWAITING_CANVAS) {
        if (blueprint.nodes.length > 0) lastDraft.current.key = key;
        return;
      }
      if (key === lastDraft.current.key) return;
      lastDraft.current.key = key;
      waiting.current = { blueprint, node_count: stepCount(blueprint) };
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(saveNow, SAVE_AFTER_MS);
    },
    [activeSessionId, saved, saveNow]
  );

  // Name the pipeline: after its template, or as the person types. An
  // empty name makes it untitled again.
  const nameSession = useCallback(
    (newTitle: string) => {
      const clean = newTitle.trim();
      setNamed({ id: activeSessionId, title: clean || UNTITLED });
      send({ title: clean });
    },
    [activeSessionId, send]
  );

  return {
    saveStatus,
    setSaveStatus,
    autosaveGraph,
    saveNow,
    title,
    nameSession,
  };
}
