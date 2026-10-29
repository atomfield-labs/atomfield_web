/**
 * A request made once per page load and shared by every caller. A
 * failed one is forgotten, so the next caller tries again.
 */
export function sharedRequest<T>(load: () => Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null;
  return () => {
    if (!pending) {
      pending = load().catch((error) => {
        pending = null;
        throw error;
      });
    }
    return pending;
  };
}
