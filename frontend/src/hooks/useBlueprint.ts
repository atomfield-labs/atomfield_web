import { useState, useEffect } from 'react';
import { pipelineService } from '../api/services';
import type { PipelineBlueprint } from '../types/api';

export function useBlueprint(activeSessionId: string) {
  const [blueprint, setBlueprint] = useState<PipelineBlueprint>({ nodes: [], edges: [] });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    if (activeSessionId === 'nanoreactor') {
      setIsLoading(true);
      pipelineService
        .getNanoreactorBlueprint()
        .then((data) => {
          if (isMounted) {
            setBlueprint(data);
            setIsLoading(false);
          }
        })
        .catch((err) => {
          console.error('Failed to fetch nanoreactor blueprint', err);
          if (isMounted) setIsLoading(false);
        });
      return () => {
        isMounted = false;
      };
    }

    // Check localStorage for saved draft
    const savedBp = localStorage.getItem(`atomfield_blueprint_${activeSessionId}`);
    if (savedBp) {
      try {
        const parsed = JSON.parse(savedBp);
        setBlueprint(parsed);
        setIsLoading(false);
        return () => {
          isMounted = false;
        };
      } catch (err) {
        console.error('Failed to parse saved blueprint from localStorage', err);
      }
    }

    // Fetch from API if not a draft
    const isClientDraft =
      activeSessionId.startsWith('pipeline_') || activeSessionId.startsWith('draft_');

    if (activeSessionId && !isClientDraft) {
      setIsLoading(true);
      pipelineService
        .getSessionBlueprint(activeSessionId)
        .then((data) => {
          if (isMounted) {
            setBlueprint(data);
            setIsLoading(false);
          }
        })
        .catch(() => {
          if (isMounted) {
            setBlueprint({ nodes: [], edges: [] });
            setIsLoading(false);
          }
        });
    } else {
      setBlueprint({ nodes: [], edges: [] });
      setIsLoading(false);
    }

    return () => {
      isMounted = false;
    };
  }, [activeSessionId]);

  return { blueprint, isLoading, setBlueprint };
}
