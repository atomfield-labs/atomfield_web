import apiClient from '../client';
import type {
  AdminQuotaUpdateRequest,
  AdminStatsResponse,
  AdminUserListResponse,
  AdminUserSummary,
} from '../../types/api';

export const adminService = {
  async getAdminStats(): Promise<AdminStatsResponse> {
    const response = await apiClient.get<AdminStatsResponse>('/api/admin/stats');
    return response.data;
  },

  async getAdminUsers(): Promise<AdminUserListResponse> {
    const response = await apiClient.get<AdminUserListResponse>('/api/admin/users');
    return response.data;
  },

  async updateUserQuota(
    userId: string,
    quotaLimit?: number,
    resetQuotaUsed?: boolean
  ): Promise<AdminUserSummary> {
    const payload: AdminQuotaUpdateRequest = {};
    if (quotaLimit !== undefined) payload.quota_limit = quotaLimit;
    if (resetQuotaUsed !== undefined) payload.reset_quota_used = resetQuotaUsed;

    const response = await apiClient.patch<AdminUserSummary>(
      `/api/admin/users/${userId}/quota`,
      payload
    );
    return response.data;
  },
};
