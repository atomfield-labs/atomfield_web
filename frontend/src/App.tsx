import { useState, useEffect, Component, type ReactNode } from 'react'

import HeroSection from './components/HeroSection'
import ScientificEngines from './components/ScientificEngines'
import SectionsContainer from './components/SectionsContainer'
import Navbar from './components/Navbar'
import SessionsDashboard from './components/dashboard/SessionsDashboard'
import AdminDashboard from './components/admin/AdminDashboard'
import PipelineEditor from './components/pipeline/PipelineEditor'
import AccountProvider from './components/auth/AccountProvider'
import AccountPage from './components/auth/AccountPage'
import SignInPage from './components/auth/SignInPage'
import PairPage from './components/pairing/PairPage'
import LabsPage from './components/labs/LabsPage'
import LabPage from './components/labs/LabPage'
import { useAccount, useSignedInAccount } from './hooks/useAccount'

// Views for a signed-in person; the landing page is open to all.
const PRIVATE_VIEWS = [
  '#dashboard',
  '#pipeline',
  '#admin',
  '#lab',
  '#account',
  '#pair',
];

const CRASH_SCREEN = [
  'p-10 text-red-600 bg-red-50 font-bold font-mono z-[9999] relative',
  'h-screen w-screen',
].join(' ');
// #pair, or #pair/<code> from an agent's link.
const PAIR_VIEW = /^#pair\/?/;
const LABS_VIEW = '#labs';
// #lab is the person's own; #lab/<id> any lab, for the owner.
const LAB_VIEW = /^#lab\/?/;
const PAGE = 'absolute inset-0 z-40 overflow-y-auto bg-slate-50';
const EDITOR = 'absolute inset-0 z-50 overflow-hidden bg-slate-50';
const LANDING = [
  'absolute inset-0 z-10 overflow-y-auto bg-slate-50',
  'selection:bg-orange-100 selection:text-orange-900',
].join(' ');

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  override state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error) {
    console.error('Caught by ErrorBoundary:', error)
  }

  override render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div className={CRASH_SCREEN}>
        <h1>CRITICAL UI CRASH</h1>
        <pre>
          {this.state.error ? String(this.state.error) : 'Unknown error'}
        </pre>
      </div>
    )
  }
}

/**
 * The address's view part (after #), followed as it changes.
 */
function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const follow = () => setHash(window.location.hash);
    window.addEventListener('hashchange', follow);
    return () => window.removeEventListener('hashchange', follow);
  }, []);
  return hash;
}

/**
 * #lab, or #lab/<id>; someone with no lab of their own sees the list.
 */
function LabView({ labId }: { labId: string }) {
  const account = useSignedInAccount();
  const id = labId || account.lab_id;
  return id ? <LabPage key={id} labId={id} /> : <LabsPage />
}

function View({ hash }: { hash: string }) {
  if (hash.startsWith('#admin')) {
    return <div className={PAGE}><AdminDashboard /></div>
  }
  if (hash.startsWith(LABS_VIEW)) {
    return <div className={PAGE}><LabsPage /></div>
  }
  if (hash.startsWith('#lab')) {
    const labId = hash.replace(LAB_VIEW, '')
    return <div className={PAGE}><LabView labId={labId} /></div>
  }
  if (hash.startsWith('#dashboard')) {
    return <div className={PAGE}><SessionsDashboard /></div>
  }
  if (hash.startsWith('#account')) {
    return <div className={PAGE}><AccountPage /></div>
  }
  if (hash.startsWith('#pair')) {
    const code = hash.replace(PAIR_VIEW, '')
    return <div className={PAGE}><PairPage code={code} /></div>
  }
  // #pipeline/new, #pipeline/new/<template id> or #pipeline/<session>.
  if (hash.startsWith('#pipeline/')) {
    const sessionId = hash.replace('#pipeline/', '')
    return (
      <div className={EDITOR}>
        <PipelineEditor sessionId={sessionId} />
      </div>
    )
  }
  return (
    <div className={LANDING}>
      <HeroSection />
      <ScientificEngines />
      <SectionsContainer />
    </div>
  )
}

/**
 * Private views wait for the account, and show sign-in to anyone
 * signed out; the landing page shows to everyone.
 */
function Shell() {
  const hash = useHash();
  const { state } = useAccount();
  const isPrivate = PRIVATE_VIEWS.some((view) => hash.startsWith(view));
  if (isPrivate && state.status === 'signed-out') return <SignInPage />
  if (isPrivate && state.status === 'loading') {
    return <main className="h-screen bg-white" />
  }
  return (
    <main className="relative w-full h-screen bg-slate-50 overflow-hidden">
      {!hash.startsWith('#pipeline') && <Navbar />}
      <View hash={hash} />
    </main>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <AccountProvider>
        <Shell />
      </AccountProvider>
    </ErrorBoundary>
  )
}

export default App
