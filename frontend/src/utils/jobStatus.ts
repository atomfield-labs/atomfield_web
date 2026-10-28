import type { JobStatus, ServerJobStatus } from '../types/api';

// How each server status is shown. A job waiting on its parents shows
// as Blocked; a job whose parent failed shows as Failed.
const DISPLAY_STATUS: Record<ServerJobStatus, JobStatus> = {
  waiting: 'Blocked',
  queued: 'Pending',
  running: 'Running',
  succeeded: 'Success',
  failed: 'Failed',
  upstream_failed: 'Failed',
  cancelled: 'Cancelled',
};

const FINISHED: ReadonlySet<JobStatus> = new Set([
  'Success',
  'Failed',
  'Cancelled',
]);

/**
 * The UI label for a status reported by the API. A job claimed by a
 * cluster agent but still waiting in the cluster's queue is "running"
 * for the server, yet not started: it shows as Pending.
 */
export function toDisplayStatus(
  status: ServerJobStatus,
  started = true
): JobStatus {
  if (status === 'running' && !started) return 'Pending';
  return DISPLAY_STATUS[status] ?? 'Pending';
}

/**
 * Whether a job in this status will never change again.
 */
export function isFinished(status: JobStatus): boolean {
  return FINISHED.has(status);
}
