import apiClient from '../client';
import type { PipelineBlueprint } from '../../types/api';

export const pipelineService = {
  async getNanoreactorBlueprint(): Promise<PipelineBlueprint> {
    const response = await apiClient.get<PipelineBlueprint>('/api/pipeline/nanoreactor/blueprint');
    return response.data;
  },

  async getModularNanoreactorBlueprint(): Promise<PipelineBlueprint> {
    const response = await apiClient.get<PipelineBlueprint>('/api/pipeline/nanoreactor_modular/blueprint');
    return response.data;
  },

  async getSessionBlueprint(sessionId: string): Promise<PipelineBlueprint> {
    const response = await apiClient.get<PipelineBlueprint>(`/api/pipeline/${sessionId}/blueprint`);
    return response.data;
  },
};
