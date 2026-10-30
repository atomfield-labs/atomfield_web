import { useState, useEffect, useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { SaveStatus, SessionMetadata, BlueprintNode, BlueprintEdge } from '../types/api';
import { saveEdge } from '../utils/graphEdges';

// This browser's list of pipelines, shown on the sessions page.
const SESSIONS_KEY = 'atomfield_sessions';
export const UNTITLED = 'Untitled pipeline';

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
 * This browser's pipelines. Old entries may be bare ids.
 */
function readSessions(): (SessionMetadata | string)[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeSessions(list: (SessionMetadata | string)[]): void {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(list));
}

function indexOf(list: (SessionMetadata | string)[], id: string): number {
  return list.findIndex((item) =>
    typeof item === 'string' ? item === id : item.id === id
  );
}

/**
 * A pipeline's name as this browser saved it.
 */
function storedTitle(id: string): string {
  const list = readSessions();
  const found = list[indexOf(list, id)];
  return found && typeof found !== 'string' ? found.title : UNTITLED;
}

/**
 * Change one pipeline's entry, adding it first if it is new.
 */
function updateSession(id: string, change: Partial<SessionMetadata>): void {
  const list = readSessions();
  const index = indexOf(list, id);
  const existing = index >= 0 ? list[index] : null;
  const base: SessionMetadata =
    existing && typeof existing !== 'string'
      ? existing
      : {
          id,
          title: UNTITLED,
          status: 'Draft',
          nodeCount: 0,
          updatedAt: new Date().toISOString(),
        };
  const updated = { ...base, ...change };
  if (index >= 0) list[index] = updated;
  else list.unshift(updated);
  writeSessions(list);
}

export function useSessionDraft(activeSessionId: string) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  // A name given in this view; otherwise the name this browser saved.
  const [named, setNamed] = useState<{ id: string; title: string } | null>(
    null
  );
  const title =
    named?.id === activeSessionId ? named.title : storedTitle(activeSessionId);

  // List a new pipeline on the sessions page.
  useEffect(() => {
    if (!activeSessionId) return;
    try {
      updateSession(activeSessionId, {});
    } catch (err) {
      console.error('Failed to register session draft', err);
    }
  }, [activeSessionId]);

  // Save the canvas in this browser as it changes.
  const autosaveGraph = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      setSaveStatus('saving');
      const serializedBlueprint = serializeGraphToBlueprint(graph.nodes, graph.edges);
      try {
        localStorage.setItem(
          `atomfield_blueprint_${activeSessionId}`,
          JSON.stringify(serializedBlueprint)
        );
        updateSession(activeSessionId, {
          nodeCount: graph.nodes.length,
          updatedAt: new Date().toISOString(),
        });
        setSaveStatus('saved');
      } catch (err) {
        console.error('Autosave failed', err);
      }
    },
    [activeSessionId]
  );

  // Name the pipeline: after its template, or as the person types.
  const nameSession = useCallback(
    (newTitle: string) => {
      const clean = newTitle.trim() || UNTITLED;
      setNamed({ id: activeSessionId, title: clean });
      try {
        updateSession(activeSessionId, { title: clean, named: true });
      } catch (err) {
        console.error('Failed to name the session', err);
      }
    },
    [activeSessionId]
  );

  const markSessionRunning = useCallback(() => {
    try {
      updateSession(activeSessionId, {
        status: 'Running',
        updatedAt: new Date().toISOString(),
      });
    } catch (err) {
      console.error('Failed to mark session as running', err);
    }
  }, [activeSessionId]);

  return {
    saveStatus,
    setSaveStatus,
    autosaveGraph,
    markSessionRunning,
    title,
    nameSession,
  };
}
