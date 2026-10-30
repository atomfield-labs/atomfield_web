import axios from 'axios';

/**
 * The API client. The web app is served from the API's own address (in
 * development through Vite's proxy), so the browser sends the sign-in
 * cookie with every request by itself: no keys are kept in the page.
 */
const client = axios.create({
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * What to tell the person about a failed request: the server's own
 * explanation when it gave one (a sentence, or the list of problems
 * FastAPI sends for a malformed request), otherwise `fallback`.
 */
export function describeError(error: unknown, fallback: string): string {
  const detail = axios.isAxiosError(error)
    ? error.response?.data?.detail
    : undefined;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const problems = detail.map((problem) => problem?.msg).filter(Boolean);
    return problems.join('; ') || fallback;
  }
  return fallback;
}

/**
 * The HTTP status a failed request got, if it got an answer at all.
 */
export function statusOf(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

export default client;
