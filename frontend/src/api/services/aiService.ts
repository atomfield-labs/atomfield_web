import apiClient from '../client';
import type { AiKeySaved, AiKeyState, AiVendor } from '../../types/api';

const KEY_ROUTE = '/api/ai/key';

// A person's own key for an AI vendor. A key only ever goes to the
// server: nothing here gets one back.
export const aiService = {
  async keyState(): Promise<AiKeyState> {
    const response = await apiClient.get<AiKeyState>(KEY_ROUTE);
    return response.data;
  },

  async saveKey(vendor: AiVendor, key: string): Promise<AiKeySaved> {
    const response = await apiClient.put<AiKeySaved>(KEY_ROUTE, {
      vendor,
      key,
    });
    return response.data;
  },

  async models(): Promise<string[]> {
    const response = await apiClient.get<string[]>(`${KEY_ROUTE}/models`);
    return response.data;
  },

  async chooseModel(model: string): Promise<AiKeyState> {
    const response = await apiClient.patch<AiKeyState>(KEY_ROUTE, { model });
    return response.data;
  },

  async removeKey(): Promise<void> {
    await apiClient.delete(KEY_ROUTE);
  },
};
