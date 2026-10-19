import apiClient from '../client';
import type {
  PipelineSubmitRequest,
  PipelineSubmitResponse,
  JobLogsResponse,
} from '../../types/api';

export const jobsService = {
  async submitPipeline(payload: PipelineSubmitRequest): Promise<PipelineSubmitResponse> {
    const response = await apiClient.post<PipelineSubmitResponse>(
      '/api/jobs/pipeline/submit',
      payload
    );
    return response.data;
  },

  async getJobLogs(jobId: string): Promise<JobLogsResponse> {
    const response = await apiClient.get<JobLogsResponse>(`/api/jobs/${jobId}/logs`);
    return response.data;
  },

  async downloadJobArtifacts(jobId: string, sessionId: string): Promise<Blob> {
    const response = await apiClient.get(`/api/jobs/${jobId}/artifacts/download`, {
      params: { session_id: sessionId },
      responseType: 'blob',
    });
    return new Blob([response.data], { type: 'application/zip' });
  },

  async getTextArtifacts(params?: { jobId?: string; sessionId?: string }): Promise<{
    session_id?: string;
    job_id?: string;
    files: Array<{ filename: string; content: string; size_bytes: number }>;
  }> {
    const url = params?.jobId ? `/api/jobs/${params.jobId}/artifacts/text` : '/api/jobs/artifacts/text';
    const response = await apiClient.get(url, {
      params: { session_id: params?.sessionId },
    });
    return response.data;
  },

  async listJobs(params?: { status?: string; limit?: number; offset?: number }) {
    const response = await apiClient.get<{ jobs: import('../../types/api').JobItem[]; total: number }>(
      '/api/jobs',
      { params }
    );
    return response.data;
  },

  async clearAllJobs(): Promise<{ status: string; message: string }> {
    const response = await apiClient.delete<{ status: string; message: string }>(
      '/api/jobs/clear'
    );
    return response.data;
  },
};
