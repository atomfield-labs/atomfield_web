import apiClient from '../client';
import type {
  PipelineSubmitRequest,
  PipelineSubmitResponse,
  JobLogsResponse,
  JobFilesResponse,
  BundleInfo,
} from '../../types/api';

export const jobsService = {
  async submitPipeline(payload: PipelineSubmitRequest): Promise<PipelineSubmitResponse> {
    const response = await apiClient.post<PipelineSubmitResponse>(
      '/api/jobs/pipeline/submit',
      payload
    );
    return response.data;
  },

  // Stop every unfinished job of a run.
  async cancelRun(runId: string): Promise<void> {
    await apiClient.post(`/api/runs/${runId}/cancel`);
  },

  async getJobLogs(jobId: string): Promise<JobLogsResponse> {
    const response = await apiClient.get<JobLogsResponse>(`/api/jobs/${jobId}/logs`);
    return response.data;
  },

  // The files of a job that can be read here.
  async listJobFiles(jobId: string): Promise<JobFilesResponse> {
    const response = await apiClient.get<JobFilesResponse>(
      `/api/jobs/${jobId}/files`
    );
    return response.data;
  },

  // One of those files, as the text it is.
  async readJobFile(jobId: string, name: string): Promise<string> {
    const response = await apiClient.get<string>(
      `/api/jobs/${jobId}/files/${encodeURIComponent(name)}`,
      { responseType: 'text' }
    );
    return response.data;
  },

  async clearAllJobs(): Promise<{ status: string; message: string }> {
    const response = await apiClient.delete<{ status: string; message: string }>(
      '/api/jobs/clear'
    );
    return response.data;
  },

  async deleteSession(sessionId: string): Promise<{ status: string; message: string }> {
    const response = await apiClient.delete<{ status: string; message: string }>(
      `/api/jobs/session/${sessionId}`
    );
    return response.data;
  },

  // How to get a run's files: a download link, or where they are.
  async getBundle(runId: string): Promise<BundleInfo> {
    const response = await apiClient.get<BundleInfo>(
      `/api/runs/${runId}/bundle`
    );
    return response.data;
  },

  // Ask for a run's zip ("Make a download link").
  async requestBundle(runId: string): Promise<BundleInfo> {
    const response = await apiClient.post<BundleInfo>(
      `/api/runs/${runId}/bundle`
    );
    return response.data;
  },
};
