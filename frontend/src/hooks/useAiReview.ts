import { useEffect, useState } from 'react';
import { describeError } from '../api/client';
import { aiService } from '../api/services';
import type { AiReview, AiReviewKind, AiReviewState } from '../types/api';
import { statusLook } from '../utils/jobStatus';

// A review takes a minute or so; the server gives up after five.
const POLL_MS = 2000;
const MAX_POLLS = 200;
const COULD_NOT_START = 'Could not start. Try again.';
const ENDED_LOOKS: ReadonlySet<string> = new Set(['done', 'failed']);

export const AI_BUTTON_LABEL: Record<AiReviewKind, string> = {
  fix: 'Fix failure',
  analysis: 'Analyze results',
};

interface Loaded {
  jobId: string;
  state: AiReviewState;
}

export interface AiReviewControls {
  // What a review would do; null if this step can't have one.
  kind: AiReviewKind | null;
  review: AiReview | null;
  starting: boolean;
  problem: string | null;
  start: () => Promise<void>;
}

/**
 * A step's AI review: what can be asked, the newest answer, and the way
 * to ask. While a review runs it asks the server how it is going.
 */
export function useAiReview(
  jobId: string | undefined,
  status: string | undefined
): AiReviewControls {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [asked, setAsked] = useState(0);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const hasEnded = ENDED_LOOKS.has(statusLook(status));

  useEffect(() => {
    if (!jobId || !hasEnded) return;
    let active = true;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const readAgain = () => {
      polls += 1;
      if (polls < MAX_POLLS) timer = setTimeout(read, POLL_MS);
    };
    const read = () => {
      aiService
        .reviewState(jobId)
        .then((state) => {
          if (!active) return;
          setLoaded({ jobId, state });
          if (state.review?.status === 'running') readAgain();
        })
        .catch(() => active && readAgain());
    };
    read();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId, hasEnded, asked]);

  const start = async () => {
    if (!jobId) return;
    setStarting(true);
    setProblem(null);
    try {
      await aiService.startReview(jobId);
      setAsked((count) => count + 1);
    } catch (error) {
      setProblem(describeError(error, COULD_NOT_START));
    } finally {
      setStarting(false);
    }
  };

  // Another step's answer must not show while this one's is on its way.
  const state = loaded && loaded.jobId === jobId ? loaded.state : null;
  return {
    kind: (hasEnded && state?.kind) || null,
    review: state?.review ?? null,
    starting,
    problem,
    start,
  };
}
