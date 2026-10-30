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

// How a step's status is drawn: one small icon, never a coloured box.
export type StatusLook =
  | 'none'
  | 'waiting'
  | 'running'
  | 'done'
  | 'failed'
  | 'stopped';

const LOOKS: Record<string, StatusLook> = {
  draft: 'none',
  ready: 'none',
  pending: 'waiting',
  blocked: 'waiting',
  running: 'running',
  success: 'done',
  completed: 'done',
  failed: 'failed',
  cancelled: 'stopped',
};

export const STATUS_TEXT: Record<StatusLook, string> = {
  none: 'Not run yet',
  waiting: 'Waiting',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  stopped: 'Cancelled',
};

/**
 * Which look a status gets, whatever its spelling or case.
 */
export function statusLook(status?: string | null): StatusLook {
  return LOOKS[(status ?? 'draft').toLowerCase()] ?? 'none';
}

export type RunPhase = 'idle' | 'running' | 'done' | 'failed' | 'cancelled';

// Where a pipeline's run stands, for the editor's header.
export interface RunProgress {
  phase: RunPhase;
  done: number;
  total: number;
}

/**
 * Where a run stands, from its steps' statuses: running while any step
 * runs or waits; afterwards, how it ended.
 */
export function runProgress(statuses: (string | undefined)[]): RunProgress {
  const looks = statuses.map(statusLook);
  const count = (look: StatusLook) =>
    looks.filter((item) => item === look).length;
  const done = count('done');
  const total = looks.length;
  let phase: RunPhase = 'idle';
  if (count('running') + count('waiting') > 0) phase = 'running';
  else if (count('failed') > 0) phase = 'failed';
  else if (count('stopped') > 0) phase = 'cancelled';
  else if (total > 0 && done === total) phase = 'done';
  return { phase, done, total };
}

const PHASE_STATUS: Record<RunPhase, JobStatus> = {
  idle: 'Draft',
  running: 'Running',
  done: 'Success',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

/**
 * One status for a whole run, read from all its steps.
 */
export function runStatus(statuses: string[]): JobStatus {
  return PHASE_STATUS[runProgress(statuses).phase];
}
