import apiClient, { statusOf } from '../client';
import type {
  SessionDetail,
  SessionSave,
  SessionSummary,
} from '../../types/api';

const NOT_FOUND = 404;

// A person's pipelines, kept on the server: everyone sees only their
// own, from any computer.
export const sessionsService = {
  async list(): Promise<SessionSummary[]> {
    const response = await apiClient.get<SessionSummary[]>('/api/sessions');
    return response.data;
  },

  // One pipeline with its draft; null if this person has none by that id.
  async get(sessionId: string): Promise<SessionDetail | null> {
    try {
      const response = await apiClient.get<SessionDetail>(
        `/api/sessions/${sessionId}`
      );
      return response.data;
    } catch (error) {
      if (statusOf(error) === NOT_FOUND) return null;
      throw error;
    }
  },

  async save(sessionId: string, change: SessionSave): Promise<void> {
    await apiClient.put(`/api/sessions/${sessionId}`, change);
  },
};
