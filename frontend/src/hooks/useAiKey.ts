import { useEffect, useState } from 'react';
import { aiService } from '../api/services';
import type { AiKeyState } from '../types/api';

/**
 * Whether AI help is on offer, and the person's saved key, without the
 * key itself. Null until it is known, or if it can't be read.
 */
export function useAiKey() {
  const [state, setState] = useState<AiKeyState | null>(null);

  useEffect(() => {
    let active = true;
    aiService
      .keyState()
      .then((found) => active && setState(found))
      .catch(() => active && setState(null));
    return () => {
      active = false;
    };
  }, []);

  return { state, setState };
}
