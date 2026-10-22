import { useEffect, useMemo, useState } from 'react';
import { catalogService } from '../api/services';
import type { TaskDefinition } from '../types/api';

// One request per page load, shared by every component that asks.
let cachedRequest: Promise<TaskDefinition[]> | null = null;

function loadTaskDefinitions(): Promise<TaskDefinition[]> {
  if (!cachedRequest) {
    cachedRequest = catalogService.listTaskDefinitions().catch((error) => {
      cachedRequest = null; // let the next caller retry
      throw error;
    });
  }
  return cachedRequest;
}

export interface TaskCatalog {
  tasks: TaskDefinition[];
  taskById: Map<string, TaskDefinition>;
  isLoading: boolean;
}

/**
 * The task catalog, loaded once and shared across components.
 */
export function useTaskDefinitions(): TaskCatalog {
  const [tasks, setTasks] = useState<TaskDefinition[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    loadTaskDefinitions()
      .then((loaded) => active && setTasks(loaded))
      .catch((error) => console.error('Failed to load task catalog', error))
      .finally(() => active && setIsLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const taskById = useMemo(
    () => new Map(tasks.map((task) => [task.id, task])),
    [tasks]
  );
  return { tasks, taskById, isLoading };
}
