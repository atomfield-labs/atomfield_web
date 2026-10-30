import apiClient from '../client';
import type { ComputeTarget, PairingView } from '../../types/api';

/**
 * Pairing a computer's agent by the short code it shows.
 */
function pairingPath(code: string): string {
  return `/api/pairings/${encodeURIComponent(code.trim())}`;
}

export const pairingService = {
  // Which computer is asking, so the person can tell it is theirs.
  async see(code: string): Promise<PairingView> {
    const response = await apiClient.get<PairingView>(pairingPath(code));
    return response.data;
  },

  // Approve it: it becomes one of the person's clusters.
  async approve(code: string, name: string): Promise<ComputeTarget> {
    const response = await apiClient.post<ComputeTarget>(pairingPath(code), {
      name,
    });
    return response.data;
  },
};
