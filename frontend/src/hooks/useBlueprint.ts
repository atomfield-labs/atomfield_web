import { useCallback, useEffect, useMemo, useState } from 'react';
import { sessionsService } from '../api/services';
import type { PipelineBlueprint, SessionDetail } from '../types/api';

const EMPTY_BLUEPRINT: PipelineBlueprint = { nodes: [], edges: [] };

/**
 * What a session opens with: its saved draft, else an empty canvas;
 * until a template replaces it (``setBlueprint``). While the draft is
 * on its way, ``saved`` is undefined: the canvas must wait, or an empty
 * canvas could be saved over the draft.
 */
export function useBlueprint(activeSessionId: string, isNew: boolean) {
  const [loaded, setLoaded] = useState<{
    id: string;
    session: SessionDetail | null;
  } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [replaced, setReplaced] = useState<{
    id: string;
    blueprint: PipelineBlueprint;
  } | null>(null);

  useEffect(() => {
    if (isNew) return;
    let active = true;
    sessionsService
      .get(activeSessionId)
      .then((session) => {
        if (active) setLoaded({ id: activeSessionId, session });
      })
      .catch((error) => {
        console.error('Failed to load the pipeline', error);
        if (active) setLoadFailed(true);
      });
    return () => {
      active = false;
    };
  }, [activeSessionId, isNew]);

  const isLoaded = loaded?.id === activeSessionId;
  const loadedHere = isLoaded ? loaded.session : undefined;
  const saved = isNew ? null : loadedHere;
  // Read once per session: the canvas reloads whenever this changes.
  const draft = useMemo(
    () => saved?.blueprint ?? EMPTY_BLUEPRINT,
    [saved]
  );
  const blueprint =
    replaced?.id === activeSessionId ? replaced.blueprint : draft;

  const setBlueprint = useCallback(
    (next: PipelineBlueprint) =>
      setReplaced({ id: activeSessionId, blueprint: next }),
    [activeSessionId]
  );

  return { saved, loadFailed, blueprint, setBlueprint };
}
