import apiClient from '../client';
import type {
  Account,
  NewScriptKey,
  ScriptKey,
  UserStatsResponse,
} from '../../types/api';

// Where the browser goes to sign in; the server sends it on to Google.
export const SIGN_IN_PATH = '/api/auth/login';
const MY_KEYS_PATH = '/api/auth/me/keys';

export const authService = {
  async getMe(): Promise<Account> {
    const response = await apiClient.get<Account>('/api/auth/me');
    return response.data;
  },

  async getStats(): Promise<UserStatsResponse> {
    const response = await apiClient.get<UserStatsResponse>(
      '/api/auth/stats'
    );
    return response.data;
  },

  async signOut(): Promise<void> {
    await apiClient.post('/api/auth/logout');
  },

  async listKeys(): Promise<ScriptKey[]> {
    const response = await apiClient.get<ScriptKey[]>(MY_KEYS_PATH);
    return response.data;
  },

  async makeKey(label: string): Promise<NewScriptKey> {
    const response = await apiClient.post<NewScriptKey>(MY_KEYS_PATH, {
      label,
    });
    return response.data;
  },

  async revokeKey(keyId: string): Promise<void> {
    await apiClient.delete(`${MY_KEYS_PATH}/${keyId}`);
  },
};
