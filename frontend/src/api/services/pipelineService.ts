import apiClient from '../client';
import type { PipelineBlueprint } from '../../types/api';

// The ready-made pipelines the server offers, named by the path that
// serves each.
export type TemplateName = 'nanoreactor' | 'nanoreactor_modular' | 'ahc';

/**
 * One ready-made pipeline: its nodes and edges, ready for the canvas.
 */
async function fetchTemplate(
  template: TemplateName
): Promise<PipelineBlueprint> {
  const response = await apiClient.get<PipelineBlueprint>(
    `/api/pipeline/${template}/blueprint`
  );
  return response.data;
}

export const pipelineService = {
  getTemplateBlueprint: fetchTemplate,

  async getNanoreactorBlueprint(): Promise<PipelineBlueprint> {
    return fetchTemplate('nanoreactor');
  },

  async getSessionBlueprint(sessionId: string): Promise<PipelineBlueprint> {
    const response = await apiClient.get<PipelineBlueprint>(
      `/api/pipeline/${sessionId}/blueprint`
    );
    return response.data;
  },
};
