import { useEffect, useState } from 'react';
import { catalogService } from '../api/services';
import type { PipelineTemplate } from '../types/api';
import { sharedRequest } from '../utils/sharedRequest';

// One request per page load, shared by every component that asks.
export const loadPipelineTemplates = sharedRequest(() =>
  catalogService.listPipelineTemplates()
);

/**
 * The ready-made pipelines of the current scripts release.
 */
export function usePipelineTemplates(): PipelineTemplate[] {
  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);

  useEffect(() => {
    let active = true;
    loadPipelineTemplates()
      .then((loaded) => active && setTemplates(loaded))
      .catch((error) =>
        console.error('Failed to load pipeline templates', error)
      );
    return () => {
      active = false;
    };
  }, []);

  return templates;
}
