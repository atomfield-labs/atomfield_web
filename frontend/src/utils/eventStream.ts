// Waits between reconnect attempts: 1 s, doubling, at most 15 s.
const RETRY_FIRST_MS = 1000;
const RETRY_MAX_MS = 15000;

/**
 * One server-sent event: its type and its data line(s).
 */
export interface StreamFrame {
  event: string;
  data: string;
}

/**
 * The server refused the stream. Worth retrying only for server-side
 * trouble; a missing key or an unknown run will not fix itself.
 */
export class StreamError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Event stream refused with HTTP ${status}`);
    this.status = status;
  }

  get retryable(): boolean {
    return this.status >= 500 || this.status === 429;
  }
}

/**
 * Parse one frame: "event: <type>" and "data: <text>" lines.
 */
export function parseFrame(text: string): StreamFrame {
  let event = 'message';
  const data: string[] = [];
  for (const line of text.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      data.push(line.slice('data:'.length).trimStart());
    }
  }
  return { event, data: data.join('\n') };
}

/**
 * Read one connection's frames until it ends or is aborted.
 *
 * fetch rather than EventSource: EventSource cannot send headers, and
 * the API key must not travel in the URL, where logs keep it.
 */
export async function readEventStream(
  url: string,
  headers: Record<string, string>,
  onFrame: (frame: StreamFrame) => void,
  signal: AbortSignal
): Promise<void> {
  const response = await fetch(url, {
    headers: { Accept: 'text/event-stream', ...headers },
    signal,
  });
  if (!response.ok || !response.body) {
    throw new StreamError(response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      onFrame(parseFrame(buffer.slice(0, end)));
      buffer = buffer.slice(end + 2);
    }
  }
}

/**
 * Resolve after `ms`, or at once if the signal aborts.
 */
function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true }
    );
  });
}

/**
 * Keep a stream open until aborted, reconnecting after drops with a
 * growing wait. Each new connection starts with a fresh snapshot, so
 * nothing missed while disconnected stays missed.
 */
export async function followEventStream(
  url: string,
  headers: Record<string, string>,
  onFrame: (frame: StreamFrame) => void,
  signal: AbortSignal
): Promise<void> {
  let waitMs = RETRY_FIRST_MS;
  const onAnyFrame = (frame: StreamFrame) => {
    waitMs = RETRY_FIRST_MS;
    onFrame(frame);
  };
  while (!signal.aborted) {
    try {
      await readEventStream(url, headers, onAnyFrame, signal);
    } catch (error) {
      const fatal = error instanceof StreamError && !error.retryable;
      if (signal.aborted || fatal) return;
      console.warn('Live updates interrupted; reconnecting', error);
    }
    await pause(waitMs, signal);
    waitMs = Math.min(waitMs * 2, RETRY_MAX_MS);
  }
}
