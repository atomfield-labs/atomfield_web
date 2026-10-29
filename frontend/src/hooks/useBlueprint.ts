import { useState, useEffect } from 'react';
import type {
  PipelineBlueprint,
  PipelineTemplate,
  TaskDefinition,
} from '../types/api';
import { templateToBlueprint } from '../utils/templates';
import { loadPipelineTemplates } from './usePipelineTemplates';
import { loadTaskDefinitions } from './useTaskDefinitions';

// The landing page's demo session shows this template of the catalog.
const DEMO_SESSION_ID = 'nanoreactor';
const DEMO_TEMPLATE_ID = 'nanoreactor';
const EMPTY_BLUEPRINT: PipelineBlueprint = { nodes: [], edges: [] };

/**
 * The demo pipeline, built from the current release's template; an
 * empty canvas if the release has none.
 */
function demoBlueprint(
  templates: PipelineTemplate[],
  tasks: TaskDefinition[]
): PipelineBlueprint {
  const demo = templates.find((item) => item.id === DEMO_TEMPLATE_ID);
  if (!demo) return EMPTY_BLUEPRINT;
  return templateToBlueprint(demo, new Map(tasks.map((t) => [t.id, t])));
}

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
 * What a session opens with: the demo template for the demo session,
 * else the draft saved in this browser, else an empty canvas.
 */
export function useBlueprint(activeSessionId: string) {
  const [blueprint, setBlueprint] = useState<PipelineBlueprint>(
    EMPTY_BLUEPRINT
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    if (activeSessionId === DEMO_SESSION_ID) {
      setIsLoading(true);
      Promise.all([loadPipelineTemplates(), loadTaskDefinitions()])
        .then(([templates, tasks]) => {
          if (!isMounted) return;
          setBlueprint(demoBlueprint(templates, tasks));
          setIsLoading(false);
        })
        .catch((err) => {
          console.error('Failed to load the demo pipeline', err);
          if (isMounted) setIsLoading(false);
        });
      return () => {
        isMounted = false;
      };
    }

    setBlueprint(savedDraft(activeSessionId) ?? EMPTY_BLUEPRINT);
    setIsLoading(false);
    return () => {
      isMounted = false;
    };
  }, [activeSessionId]);

  return { blueprint, isLoading, setBlueprint };
}
