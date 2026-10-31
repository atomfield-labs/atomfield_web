import { useEffect, useState } from 'react';
import { catalogService } from '../api/services';
import type { Workflow } from '../types/api';

/**
 * The workflows this person may use; null until they have loaded. Read
 * afresh each time, so one just given shows without a reload.
 */
export function useWorkflows(): Workflow[] | null {
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);

  useEffect(() => {
    let active = true;
    catalogService
      .listWorkflows()
      .then((loaded) => active && setWorkflows(loaded))
      .catch((error) => console.error('Failed to load workflows', error));
    return () => {
      active = false;
    };
  }, []);

  return workflows;
}
