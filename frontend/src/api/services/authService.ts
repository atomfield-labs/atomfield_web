import apiClient from '../client';
import type { Account, UserStatsResponse } from '../../types/api';

// Where the browser goes to sign in; the server sends it on to Google.
export const SIGN_IN_PATH = '/api/auth/login';

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
};
