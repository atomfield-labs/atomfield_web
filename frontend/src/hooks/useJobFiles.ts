import { useEffect, useState } from 'react';
import { jobsService } from '../api/services';
import type { JobFilesResponse } from '../types/api';

const NO_FILES: JobFilesResponse = { files: [], others: 0 };

interface Listing {
  jobId: string;
  found: JobFilesResponse;
}

/**
 * A job's files that can be read here. A job uploads them when it
 * ends, so the list is asked for again whenever its status changes.
 */
export function useJobFiles(
  jobId: string | undefined,
  status: string | undefined
): JobFilesResponse {
  const [listing, setListing] = useState<Listing | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    jobsService
      .listJobFiles(jobId)
      .then((found) => active && setListing({ jobId, found }))
      .catch(() => active && setListing({ jobId, found: NO_FILES }));
    return () => {
      active = false;
    };
  }, [jobId, status]);

  // Another job's list must not show while this one's is on its way.
  return listing && listing.jobId === jobId ? listing.found : NO_FILES;
}
