import type {
  JobEvent,
  JobStatus,
  RunSnapshot,
  ServerJobStatus,
} from '../types/api';
import { isFinished, toDisplayStatus } from './jobStatus';

/**
 * A job whose shown status must change.
 */
export interface StatusChange {
  jobId: string;
  status: JobStatus;
}

/**
 * The statuses shown for one run, kept in step with the server's
 * numbering: a job's state is applied only if its number is newer than
 * the one shown, so late, repeated or reordered events change nothing.
 */
export class RunView {
  readonly shownSeq = new Map<string, number>();
  readonly shown = new Map<string, JobStatus>();
  jobIds: string[] = [];

  /**
   * Take a snapshot (sent on every connect, and to repair a gap).
   */
  applySnapshot(snapshot: RunSnapshot): StatusChange[] {
    this.jobIds = snapshot.jobs.map((job) => job.job_id);
    return snapshot.jobs.flatMap((job) =>
      this.apply(job.job_id, job.status, snapshot.seq, true)
    );
  }

  /**
   * Take one live event.
   */
  applyEvent(event: JobEvent): StatusChange[] {
    return this.apply(event.job_id, event.status, event.seq, false);
  }

  /**
   * Record a job's state if newer; report it if the shown status
   * changes. A snapshot's number covers every job in it, so it may
   * equal the number shown; an event must be strictly newer.
   */
  apply(
    jobId: string,
    serverStatus: ServerJobStatus,
    seq: number,
    fromSnapshot: boolean
  ): StatusChange[] {
    const last = this.shownSeq.get(jobId) ?? -1;
    if (fromSnapshot ? seq < last : seq <= last) return [];
    this.shownSeq.set(jobId, seq);
    const status = toDisplayStatus(serverStatus);
    if (this.shown.get(jobId) === status) return [];
    this.shown.set(jobId, status);
    return [{ jobId, status }];
  }

  /**
   * Whether every job of the run has reached a status that never
   * changes again.
   */
  get allFinished(): boolean {
    return (
      this.jobIds.length > 0 &&
      this.jobIds.every((jobId) => {
        const status = this.shown.get(jobId);
        return status !== undefined && isFinished(status);
      })
    );
  }
}
