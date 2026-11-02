import apiClient from '../client';
import type {
  AiKeySaved,
  AiKeyState,
  AiReview,
  AiReviewState,
  AiVendor,
} from '../../types/api';

const KEY_ROUTE = '/api/ai/key';

/**
 * Where a job's reviews live.
 */
function reviewsRoute(jobId: string): string {
  return `/api/jobs/${jobId}/ai-reviews`;
}

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

  // What can be asked about a step, and its newest answer.
  async reviewState(jobId: string): Promise<AiReviewState> {
    const response = await apiClient.get<AiReviewState>(
      `${reviewsRoute(jobId)}/latest`
    );
    return response.data;
  },

  // One click: it answers at once, and the work carries on afterwards.
  async startReview(jobId: string): Promise<AiReview> {
    const response = await apiClient.post<AiReview>(reviewsRoute(jobId));
    return response.data;
  },

  // Opens in its own tab: the browser's cookie is all it needs.
  sentTextLink(jobId: string, reviewId: string): string {
    return `${reviewsRoute(jobId)}/${reviewId}/sent`;
  },
};
