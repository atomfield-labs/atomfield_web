import apiClient from '../client';
import type { ComputeTarget, TargetToken } from '../../types/api';

// Where runs can execute: the shared server and the user's own
// clusters or computers.
export const targetsService = {
  async list(): Promise<ComputeTarget[]> {
    const response = await apiClient.get<ComputeTarget[]>('/api/targets');
    return response.data;
  },

  // The token in the answer is shown this once.
  async create(name: string, kind: 'slurm' | 'local'): Promise<TargetToken> {
    const response = await apiClient.post<TargetToken>('/api/targets', {
      name,
      kind,
    });
    return response.data;
  },

  async newToken(targetId: string): Promise<TargetToken> {
    const response = await apiClient.post<TargetToken>(
      `/api/targets/${targetId}/token`
    );
    return response.data;
  },

  async remove(targetId: string): Promise<void> {
    await apiClient.delete(`/api/targets/${targetId}`);
  },
};
