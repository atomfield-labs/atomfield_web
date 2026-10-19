import { useState, useEffect, useCallback } from 'react';
import { authService } from '../api/services';

export function useQuota() {
  const [quota, setQuota] = useState<number | null>(null);

  useEffect(() => {
    authService
      .getQuota()
      .then((data) => setQuota(data.runsRemaining))
      .catch(() => {
        // Silently handle quota check failure in local/offline modes
      });
  }, []);

  const decrementQuota = useCallback(() => {
    setQuota((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  return { quota, decrementQuota };
}
