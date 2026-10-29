import apiClient from '../client';
import type { PipelineTemplate, TaskDefinition } from '../../types/api';

export const catalogService = {
  async listTaskDefinitions(): Promise<TaskDefinition[]> {
    const response = await apiClient.get<TaskDefinition[]>(
      '/api/task-definitions'
    );
    return Array.isArray(response.data) ? response.data : [];
  },

  async listPipelineTemplates(): Promise<PipelineTemplate[]> {
    const response = await apiClient.get<PipelineTemplate[]>(
      '/api/pipeline-templates'
    );
    return Array.isArray(response.data) ? response.data : [];
  },
};
