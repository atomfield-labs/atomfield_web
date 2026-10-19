import { useEffect } from 'react';
import { jobsService } from '../api/services';

interface UseJobPollingOptions {
  activeJobMap: Record<string, string>;
  activePipelineId: string | null;
  onUpdateExecution: (
    uiId: string,
    status: string,
    logs?: string,
    artifacts?: string[],
    jobId?: string
  ) => void;
  onUpdateSelectedNode: (updater: (prev: any) => any) => void;
  onAllFinished?: () => void;
  intervalMs?: number;
}

export function useJobPolling({
  activeJobMap,
  activePipelineId,
  onUpdateExecution,
  onUpdateSelectedNode,
  onAllFinished,
  intervalMs = 1500,
}: UseJobPollingOptions) {
  useEffect(() => {
    if (Object.keys(activeJobMap).length === 0) return;

    let isSubscribed = true;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      let allFinished = true;

      for (const [uiId, jobId] of Object.entries(activeJobMap)) {
        if (!isSubscribed) return;
        try {
          const { status: rawStatus, logs, artifacts } = await jobsService.getJobLogs(jobId);
          const lower = (rawStatus || '').toLowerCase();
          const status = (lower === 'success' || lower === 'completed')
            ? 'Success'
            : (lower === 'running')
            ? 'Running'
            : (lower === 'failed')
            ? 'Failed'
            : (rawStatus || 'Pending');

          if (isSubscribed) {
            onUpdateExecution(uiId, status, logs, artifacts, jobId);

            onUpdateSelectedNode((prev: any) => {
              if (
                prev &&
                (prev.id === uiId ||
                  prev.ui_id === uiId ||
                  prev.script_id === uiId ||
                  prev.data?.script_id === uiId ||
                  prev.data?.originalData?.ui_id === uiId ||
                  prev.data?.originalData?.id === uiId)
              ) {
                return {
                  ...prev,
                  status,
                  logs,
                  artifacts,
                  job_id: jobId,
                  pipeline_id: activePipelineId || prev.pipeline_id,
                  data: {
                    ...(prev.data || {}),
                    status,
                    logs,
                    artifacts,
                    job_id: jobId,
                    pipeline_id: activePipelineId || prev.pipeline_id,
                  },
                };
              }
              return prev;
            });
          }

          if (status !== 'Success' && status !== 'Failed') {
            allFinished = false;
          }
        } catch (err) {
          console.error(`Polling error for job ${jobId}:`, err);
        }
      }

      if (allFinished && activePipelineId) {
        try {
          const raw = localStorage.getItem('atomfield_sessions');
          if (raw) {
            const list = JSON.parse(raw);
            const idx = list.findIndex((item: any) =>
              typeof item === 'string' ? item === activePipelineId : item.id === activePipelineId
            );
            if (idx >= 0) {
              list[idx].status = 'Success';
              list[idx].updatedAt = new Date().toISOString();
              localStorage.setItem('atomfield_sessions', JSON.stringify(list));
            }
          }
        } catch (e) {
          console.error('Failed to update session status in storage', e);
        }
        if (onAllFinished) {
          onAllFinished();
        }
      }

      if (isSubscribed && !allFinished) {
        timerId = setTimeout(poll, intervalMs);
      }
    };

    poll();

    return () => {
      isSubscribed = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [activeJobMap, activePipelineId, onUpdateExecution, onUpdateSelectedNode, intervalMs]);
}
