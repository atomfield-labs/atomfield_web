import { useState, useEffect, Component, type ReactNode } from 'react'

import HeroSection from './components/HeroSection'
import SectionsContainer from './components/SectionsContainer'
import Navbar from './components/Navbar'
import SessionsDashboard from './components/dashboard/SessionsDashboard'
import AdminDashboard from './components/admin/AdminDashboard'
import PipelineEditor from './components/pipeline/PipelineEditor'

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<{children: ReactNode}, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { hasError: false, error: null }
  static getDerivedStateFromError(error: Error): ErrorBoundaryState { return { hasError: true, error } }
  override componentDidCatch(error: Error) { console.error("Caught by ErrorBoundary:", error) }
  override render() {
    if (this.state.hasError) return <div className="p-10 text-red-600 bg-red-50 font-bold font-mono z-[9999] relative h-screen w-screen"><h1>CRITICAL UI CRASH</h1><pre>{this.state.error ? String(this.state.error) : 'Unknown error'}</pre></div>
    return this.props.children
  }
}

function App() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    const handleHashChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  return (
    <ErrorBoundary>
      <main className="relative w-full h-screen bg-slate-50 overflow-hidden">
        
        {!hash.startsWith('#pipeline') && <Navbar />}

        {/* Dynamic Views */}
        {hash.startsWith('#admin') ? (
          <div className="absolute inset-0 z-40 overflow-y-auto bg-slate-50">
            <AdminDashboard />
          </div>
        ) : hash.startsWith('#dashboard') ? (
          <div className="absolute inset-0 z-40 overflow-y-auto bg-slate-50">
            <SessionsDashboard />
          </div>
        ) : hash.startsWith('#pipeline/new') ? (
          <div className="absolute inset-0 z-50 overflow-hidden bg-slate-50">
            <PipelineEditor />
          </div>
        ) : hash.startsWith('#pipeline/') ? (
          <div className="absolute inset-0 z-50 overflow-hidden bg-slate-50">
            <PipelineEditor sessionId={hash.replace('#pipeline/', '')} />
          </div>
        ) : (
          <div className="absolute inset-0 z-10 overflow-y-auto bg-slate-50 selection:bg-orange-100 selection:text-orange-900">
            <HeroSection />
            <SectionsContainer />
          </div>
        )}

      </main>
    </ErrorBoundary>
  )
}

export default App
