import { createContext, useContext } from 'react';
import type { Account } from '../types/api';

// Why a sign-in was refused, as the server tells the web app.
export type SignInProblem =
  | 'expired'
  | 'denied'
  | 'outside'
  | 'disabled'
  | 'failed'
  | 'unavailable'
  | 'busy';

export type AccountState =
  | { status: 'loading' }
  | {
      status: 'signed-out';
      problem: SignInProblem | null;
      // The address refused, so the person can give it to their admin.
      refusedEmail?: string | null;
    }
  | { status: 'signed-in'; account: Account };

export interface AccountContextValue {
  state: AccountState;
  // Off to Google; afterwards back to where the person was.
  signIn: () => void;
  signOut: () => Promise<void>;
  // Read the account again, e.g. after its quota changed.
  refresh: () => Promise<void>;
}

export const AccountContext = createContext<AccountContextValue | null>(
  null
);

/**
 * Who is signed in, and how to sign in and out. The one place the web
 * app learns this; every view asks here.
 */
export function useAccount(): AccountContextValue {
  const value = useContext(AccountContext);
  if (!value) {
    throw new Error('useAccount needs an AccountProvider above it');
  }
  return value;
}

/**
 * The signed-in person, for views shown only once someone is signed
 * in (App renders them only then).
 */
export function useSignedInAccount(): Account {
  const { state } = useAccount();
  if (state.status !== 'signed-in') {
    throw new Error('This view is shown only to a signed-in person');
  }
  return state.account;
}
