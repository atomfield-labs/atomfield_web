import { useCallback, useMemo, useState } from 'react';
import type { PipelineBlueprint } from '../types/api';

const EMPTY_BLUEPRINT: PipelineBlueprint = { nodes: [], edges: [] };

/**
 * The draft of a session saved in this browser, if any.
 */
function savedDraft(sessionId: string): PipelineBlueprint | null {
  const saved = localStorage.getItem(`atomfield_blueprint_${sessionId}`);
  if (!saved) return null;
  try {
    return JSON.parse(saved);
  } catch (err) {
    console.error('Failed to parse saved blueprint from localStorage', err);
    return null;
  }
}

/**
 * What a session opens with: the draft saved in this browser, else an
 * empty canvas; until a template replaces it (``setBlueprint``).
 */
export function useBlueprint(activeSessionId: string) {
  // Read once per session: the canvas reloads whenever this changes.
  const draft = useMemo(
    () => savedDraft(activeSessionId) ?? EMPTY_BLUEPRINT,
    [activeSessionId]
  );
  const [replaced, setReplaced] = useState<{
    id: string;
    blueprint: PipelineBlueprint;
  } | null>(null);
  const blueprint =
    replaced?.id === activeSessionId ? replaced.blueprint : draft;

  const setBlueprint = useCallback(
    (next: PipelineBlueprint) =>
      setReplaced({ id: activeSessionId, blueprint: next }),
    [activeSessionId]
  );

  return { blueprint, setBlueprint };
}
