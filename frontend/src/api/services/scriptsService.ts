import apiClient from '../client';
import type { ScriptManifestItem } from '../../types/api';

export const scriptsService = {
  async getAvailableScripts(): Promise<ScriptManifestItem[]> {
    const response = await apiClient.get<ScriptManifestItem[]>('/api/scripts/available');
    return Array.isArray(response.data) ? response.data : [];
  },
};
