import apiClient from '../client';
import type { TaskDefinition } from '../../types/api';

export const catalogService = {
  async listTaskDefinitions(): Promise<TaskDefinition[]> {
    const response = await apiClient.get<TaskDefinition[]>(
      '/api/task-definitions'
    );
    return Array.isArray(response.data) ? response.data : [];
  },
};
