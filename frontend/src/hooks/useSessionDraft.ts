import { useState, useEffect, useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { SaveStatus, SessionMetadata, BlueprintNode, BlueprintEdge } from '../types/api';

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
        script_name: data.filename || data.script_id || data.label,
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
    edges: edges.map((edge) => ({
      id: edge.id,
      upstream_ui_id: edge.source,
      downstream_ui_id: edge.target,
    })),
  };
}

export function useSessionDraft(activeSessionId: string) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  // Register session entry in atomfield_sessions list if not present
  useEffect(() => {
    if (!activeSessionId || activeSessionId === 'nanoreactor') return;

    try {
      const raw = localStorage.getItem('atomfield_sessions');
      const list: any[] = raw ? JSON.parse(raw) : [];
      const exists = list.some((item: any) =>
        typeof item === 'string' ? item === activeSessionId : item.id === activeSessionId
      );

      if (!exists) {
        const newSessionMeta: SessionMetadata = {
          id: activeSessionId,
          title: 'Untitled Pipeline',
          status: 'Draft',
          nodeCount: 0,
          updatedAt: new Date().toISOString(),
        };
        list.unshift(newSessionMeta);
        localStorage.setItem('atomfield_sessions', JSON.stringify(list));
      }
    } catch (err) {
      console.error('Failed to register session draft', err);
    }
  }, [activeSessionId]);

  // Autosave graph to localStorage
  const autosaveGraph = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      if (activeSessionId === 'nanoreactor') return;

      setSaveStatus('saving');
      const serializedBlueprint = serializeGraphToBlueprint(graph.nodes, graph.edges);

      try {
        localStorage.setItem(
          `atomfield_blueprint_${activeSessionId}`,
          JSON.stringify(serializedBlueprint)
        );

        const raw = localStorage.getItem('atomfield_sessions');
        const list: any[] = raw ? JSON.parse(raw) : [];

        const firstScript = graph.nodes[0]?.data?.label || 'Custom Script';
        const title =
          graph.nodes.length === 0
            ? 'Untitled Pipeline'
            : graph.nodes.length > 1
            ? `${firstScript} + ${graph.nodes.length - 1} more`
            : String(firstScript);

        const sessionIndex = list.findIndex((item: any) =>
          typeof item === 'string' ? item === activeSessionId : item.id === activeSessionId
        );

        const existingStatus = (sessionIndex >= 0 && list[sessionIndex].status) ? list[sessionIndex].status : 'Draft';
        const sessionMeta: SessionMetadata = {
          id: activeSessionId,
          title,
          status: existingStatus,
          nodeCount: graph.nodes.length,
          updatedAt: new Date().toISOString(),
        };

        if (sessionIndex >= 0) {
          list[sessionIndex] = { ...list[sessionIndex], ...sessionMeta };
        } else {
          list.unshift(sessionMeta);
        }

        localStorage.setItem('atomfield_sessions', JSON.stringify(list));
        setSaveStatus('saved');
      } catch (err) {
        console.error('Autosave failed', err);
      }
    },
    [activeSessionId]
  );

  const markSessionRunning = useCallback(() => {
    try {
      const raw = localStorage.getItem('atomfield_sessions');
      const list: any[] = raw ? JSON.parse(raw) : [];
      const sessionIndex = list.findIndex((item: any) =>
        typeof item === 'string' ? item === activeSessionId : item.id === activeSessionId
      );
      if (sessionIndex >= 0) {
        list[sessionIndex].status = 'Running';
        list[sessionIndex].updatedAt = new Date().toISOString();
        localStorage.setItem('atomfield_sessions', JSON.stringify(list));
      }
    } catch (err) {
      console.error('Failed to mark session as running', err);
    }
  }, [activeSessionId]);

  return { saveStatus, setSaveStatus, autosaveGraph, markSessionRunning };
}
