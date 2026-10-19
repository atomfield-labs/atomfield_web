import apiClient from '../client';
import type {
  ApiKeyCreateResponse,
  ApiKeyInfo,
  QuotaResponse,
  UserStatsResponse,
} from '../../types/api';

const API_KEY_STORAGE_KEY = 'atomfield_api_key';

export const authService = {
  getStoredApiKey(): string | null {
    return localStorage.getItem(API_KEY_STORAGE_KEY);
  },

  setStoredApiKey(key: string): void {
    localStorage.setItem(API_KEY_STORAGE_KEY, key.trim());
  },

  removeStoredApiKey(): void {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  },

  async createApiKey(label?: string): Promise<ApiKeyCreateResponse> {
    const response = await apiClient.post<ApiKeyCreateResponse>('/api/auth/keys', {
      label: label || 'Web Session',
    });
    return response.data;
  },

  async getMe(): Promise<ApiKeyInfo> {
    const response = await apiClient.get<ApiKeyInfo>('/api/auth/me');
    return response.data;
  },

  async getStats(): Promise<UserStatsResponse> {
    const response = await apiClient.get<UserStatsResponse>('/api/auth/stats');
    return response.data;
  },

  async getQuota(): Promise<QuotaResponse> {
    const response = await apiClient.get<QuotaResponse>('/api/auth/quota');
    return response.data;
  },
};
