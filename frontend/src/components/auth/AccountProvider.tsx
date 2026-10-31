import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import axios from 'axios';
import apiClient from '../../api/client';
import { authService, SIGN_IN_PATH } from '../../api/services/authService';
import {
  AccountContext,
  type AccountState,
  type SignInProblem,
} from '../../hooks/useAccount';

// The query parameters the server adds when it refused a sign-in.
const SIGN_IN_ERROR = 'sign_in_error';
const SIGN_IN_EMAIL = 'sign_in_email';
// Where the person was when they set off to sign in.
const RETURN_TO_KEY = 'atomfield_return_to';
// Where a refused sign-in is shown if nothing was remembered.
const FIRST_VIEW = '#dashboard';
const UNAUTHORIZED = 401;

interface Refusal {
  problem: SignInProblem | null;
  refusedEmail?: string | null;
}

/**
 * Take the server's reason for a refused sign-in out of the address,
 * so a reload does not show it again.
 */
function takeSignInProblem(): Refusal {
  const url = new URL(window.location.href);
  const problem = url.searchParams.get(SIGN_IN_ERROR);
  if (problem === null) return { problem: null };
  const refusedEmail = url.searchParams.get(SIGN_IN_EMAIL);
  url.searchParams.delete(SIGN_IN_ERROR);
  url.searchParams.delete(SIGN_IN_EMAIL);
  window.history.replaceState(null, '', url);
  return { problem: problem as SignInProblem, refusedEmail };
}

// Read once, when the page loads: the server put it there on its way
// back from Google.
const REFUSAL_AT_LOAD = takeSignInProblem();

/**
 * Back to the view the person left to sign in. After a refusal they
 * stay on it, seeing why; after success it is forgotten.
 */
function returnToSavedView(signedIn: boolean): void {
  const saved = sessionStorage.getItem(RETURN_TO_KEY);
  if (signedIn) {
    sessionStorage.removeItem(RETURN_TO_KEY);
    if (saved) window.location.hash = saved;
  } else if (REFUSAL_AT_LOAD.problem) {
    window.location.hash = saved || FIRST_VIEW;
  }
}

/**
 * Ask the server who is signed in on this browser.
 */
async function readAccount(refusal: Refusal): Promise<AccountState> {
  try {
    return { status: 'signed-in', account: await authService.getMe() };
  } catch {
    return { status: 'signed-out', ...refusal };
  }
}

export default function AccountProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [state, setState] = useState<AccountState>({ status: 'loading' });

  useEffect(() => {
    void readAccount(REFUSAL_AT_LOAD).then((found) => {
      setState(found);
      returnToSavedView(found.status === 'signed-in');
    });
  }, []);

  // A sign-in can end while the app is open (it expired, or the person
  // signed out in another tab): any refused request shows sign-in.
  useEffect(() => {
    const interceptor = apiClient.interceptors.response.use(
      (response) => response,
      (error) => {
        const refused =
          axios.isAxiosError(error) &&
          error.response?.status === UNAUTHORIZED;
        if (refused) setState({ status: 'signed-out', problem: null });
        return Promise.reject(error);
      }
    );
    return () => apiClient.interceptors.response.eject(interceptor);
  }, []);

  const signIn = useCallback(() => {
    sessionStorage.setItem(RETURN_TO_KEY, window.location.hash);
    window.location.assign(SIGN_IN_PATH);
  }, []);

  const signOut = useCallback(async () => {
    await authService.signOut();
    setState({ status: 'signed-out', problem: null });
    window.location.hash = '';
  }, []);

  const refresh = useCallback(async () => {
    setState(await readAccount({ problem: null }));
  }, []);

  const value = useMemo(
    () => ({ state, signIn, signOut, refresh }),
    [state, signIn, signOut, refresh]
  );
  return (
    <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
  );
}
