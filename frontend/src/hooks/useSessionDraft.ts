import { useState, useCallback, useRef } from 'react';
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
// A saved draft or a template is on its way onto the canvas; what first
// appears there is that, not an edit.
const AWAITING_CANVAS = 'awaiting canvas';

/**
 * How many steps a draft has: its input files don't count.
 */
function stepCount(blueprint: PipelineBlueprint): number {
  return blueprint.nodes.filter((node) => STEP_TYPES.has(node.type ?? ''))
    .length;
}

// One draft as three moments: on the canvas now, last stored on the
// server, and as it opened (leaving that unchanged loses no work).
interface DraftKeys {
  id: string;
  current: string;
  stored: string;
  opened: string;
}

interface Titles {
  id: string;
  shown: string;
  stored: string;
  opened: string;
}

/**
 * A pipeline being edited. The server keeps it only when asked: by Save,
 * or by Run, which needs it stored. So opening a pipeline or a template,
 * or changing one, leaves no card until then.
 */
export function useSessionDraft(
  activeSessionId: string,
  saved: SessionDetail | null | undefined
) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const savedTitle = saved?.title || UNTITLED;
  const [titles, setTitles] = useState<Titles | null>(null);
  const titlesNow =
    titles?.id === activeSessionId
      ? titles
      : {
          id: activeSessionId,
          shown: savedTitle,
          stored: savedTitle,
          opened: savedTitle,
        };
  const [graphUnsaved, setGraphUnsaved] = useState(false);
  const [graphEdited, setGraphEdited] = useState(false);
  const [storedHere, setStoredHere] = useState<string | null>(null);
  const keys = useRef<DraftKeys | null>(null);
  const latest = useRef<PipelineBlueprint>({ nodes: [], edges: [] });
  // One save at a time, so they reach the server in order.
  const sending = useRef<Promise<boolean>>(Promise.resolve(true));

  const keysFor = useCallback((): DraftKeys => {
    if (keys.current?.id !== activeSessionId) {
      const hasDraft = (saved?.blueprint?.nodes?.length ?? 0) > 0;
      const start = hasDraft ? AWAITING_CANVAS : EMPTY_DRAFT;
      keys.current = {
        id: activeSessionId,
        current: start,
        stored: start,
        opened: start,
      };
    }
    return keys.current;
  }, [activeSessionId, saved]);

  const showKeys = useCallback((now: DraftKeys) => {
    setGraphUnsaved(
      now.stored !== AWAITING_CANVAS && now.current !== now.stored
    );
    setGraphEdited(
      now.opened !== AWAITING_CANVAS && now.current !== now.opened
    );
  }, []);

  const changeTitles = useCallback(
    (change: Partial<Titles>) =>
      setTitles((previous) => ({
        ...(previous?.id === activeSessionId
          ? previous
          : {
              id: activeSessionId,
              shown: savedTitle,
              stored: savedTitle,
              opened: savedTitle,
            }),
        ...change,
      })),
    [activeSessionId, savedTitle]
  );

  // Note what the canvas now holds.
  const trackGraph = useCallback(
    (graph: { nodes: Node[]; edges: Edge[] }) => {
      const now = keysFor();
      const blueprint = serializeGraphToBlueprint(graph.nodes, graph.edges);
      latest.current = blueprint;
      now.current = draftKey(blueprint);
      if (blueprint.nodes.length > 0) {
        if (now.stored === AWAITING_CANVAS) now.stored = now.current;
        if (now.opened === AWAITING_CANVAS) now.opened = now.current;
      }
      showKeys(now);
    },
    [keysFor, showKeys]
  );

  // Store the pipeline as it stands. True if the server now has it.
  const save = useCallback((): Promise<boolean> => {
    const blueprint = latest.current;
    const key = draftKey(blueprint);
    const name = titlesNow.shown;
    const change: SessionSave = {
      title: name === UNTITLED ? '' : name,
      blueprint,
      node_count: stepCount(blueprint),
    };
    setSaveStatus('saving');
    sending.current = sending.current
      .then(() => sessionsService.save(activeSessionId, change))
      .then(
        () => {
          const now = keysFor();
          now.stored = key;
          now.opened = key;
          showKeys(now);
          changeTitles({ stored: name, opened: name });
          setStoredHere(activeSessionId);
          setSaveStatus('saved');
          return true;
        },
        (error) => {
          console.error('Save failed', error);
          setSaveStatus('failed');
          return false;
        }
      );
    return sending.current;
  }, [activeSessionId, titlesNow.shown, keysFor, showKeys, changeTitles]);

  // A template is about to open: it is not an edit, though it isn't
  // stored either, and the pipeline takes its name.
  const openTemplate = useCallback(
    (templateTitle: string) => {
      keysFor().opened = AWAITING_CANVAS;
      changeTitles({ shown: templateTitle, opened: templateTitle });
    },
    [keysFor, changeTitles]
  );

  // Name the pipeline as the person types. An empty name makes it
  // untitled again.
  const nameSession = useCallback(
    (newTitle: string) =>
      changeTitles({ shown: newTitle.trim() || UNTITLED }),
    [changeTitles]
  );

  return {
    saveStatus,
    save,
    trackGraph,
    openTemplate,
    nameSession,
    title: titlesNow.shown,
    // Whether there is anything to store.
    unsaved: graphUnsaved || titlesNow.shown !== titlesNow.stored,
    // Whether leaving now would lose work.
    edited: graphEdited || titlesNow.shown !== titlesNow.opened,
    isStored: Boolean(saved) || storedHere === activeSessionId,
  };
}
