import { useEffect } from 'react';
import { jobsService } from '../api/services';
import type { JobEvent, JobStatus, RunSnapshot } from '../types/api';
import { followEventStream } from '../utils/eventStream';
import type { StreamFrame } from '../utils/eventStream';
import { isFinished } from '../utils/jobStatus';
import { RunView } from '../utils/runView';
import type { StatusChange } from '../utils/runView';

type ExecutionHandler = (
  uiId: string,
  status: string,
  logs?: string,
  artifacts?: string[],
  jobId?: string
) => void;

interface UseRunEventsOptions {
  runId: string | null;
  activeJobMap: Record<string, string>;
  activePipelineId: string | null;
  onUpdateExecution: ExecutionHandler;
  onUpdateSelectedNode: (updater: (prev: any) => any) => void;
  onAllFinished?: () => void;
}

/**
 * Whether the selected node is the one with this UI id.
 */
function isNode(node: any, uiId: string): boolean {
  if (!node) return false;
  const ids = [
    node.id,
    node.ui_id,
    node.script_id,
    node.data?.script_id,
    node.data?.originalData?.ui_id,
    node.data?.originalData?.id,
  ];
  return ids.includes(uiId);
}

/**
 * Copy a job's new state onto the selected node, if it is that job's.
 * Fields left undefined (logs of a running job) keep their old value.
 */
function withExecution(
  node: any,
  uiId: string,
  changes: Record<string, unknown>
): any {
  if (!isNode(node, uiId)) return node;
  const defined = Object.fromEntries(
    Object.entries(changes).filter(([, value]) => value !== undefined)
  );
  return { ...node, ...defined, data: { ...(node.data || {}), ...defined } };
}

/**
 * Turn a stream frame into status changes.
 */
function changesIn(frame: StreamFrame, view: RunView): StatusChange[] {
  if (frame.event === 'snapshot') {
    return view.applySnapshot(JSON.parse(frame.data) as RunSnapshot);
  }
  if (frame.event === 'job') {
    return view.applyEvent(JSON.parse(frame.data) as JobEvent);
  }
  return [];
}

/**
 * Follow a run's live event stream and show each job change on its
 * node. Replaces polling: the server says when something changed.
 * Logs and file lists are fetched once, when a job finishes.
 */
export function useRunEvents({
  runId,
  activeJobMap,
  activePipelineId,
  onUpdateExecution,
  onUpdateSelectedNode,
  onAllFinished,
}: UseRunEventsOptions) {
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let disposed = false;
    const view = new RunView();
    const uiIdOf = new Map(
      Object.entries(activeJobMap).map(([uiId, jobId]) => [jobId, uiId])
    );

    const render = async (jobId: string, status: JobStatus) => {
      const uiId = uiIdOf.get(jobId);
      if (!uiId) return;
      const details = isFinished(status)
        ? await jobsService.getJobLogs(jobId).catch(() => undefined)
        : undefined;
      if (disposed) return;
      const { logs, artifacts } = details ?? {};
      onUpdateExecution(uiId, status, logs, artifacts, jobId);
      onUpdateSelectedNode((prev) =>
        withExecution(prev, uiId, {
          status,
          logs,
          artifacts,
          job_id: jobId,
          pipeline_id: activePipelineId ?? undefined,
        })
      );
    };

    const onFrame = (frame: StreamFrame) => {
      for (const change of changesIn(frame, view)) {
        void render(change.jobId, change.status);
      }
      if (!view.allFinished) return;
      // Nothing can change any more: close the stream.
      controller.abort();
      onAllFinished?.();
    };

    const url = `/api/runs/${runId}/events`;
    void followEventStream(url, onFrame, controller.signal);
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [
    runId,
    activeJobMap,
    activePipelineId,
    onUpdateExecution,
    onUpdateSelectedNode,
    onAllFinished,
  ]);
}
