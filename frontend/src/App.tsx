import { Canvas } from '@react-three/fiber'
import { ScrollControls, Scroll } from '@react-three/drei'
import { Suspense, useState, useEffect, Component, type ReactNode } from 'react'

// ... existing imports ...
import PESTerrain from './animations/PESTerrain'
import JablonskiDiagram from './animations/JablonskiDiagram'
import PolymerMelt from './animations/PolymerMelt'
import IonLattice from './animations/IonLattice'
import HeroSection from './components/HeroSection'
import SectionsContainer from './components/SectionsContainer'
import ScrollSnapper from './components/ScrollSnapper'
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

function Scene() {
  return (
    <>
      <ScrollSnapper />
      <ambientLight intensity={1.0} />
      <directionalLight position={[10, 15, 10]} intensity={2.0} color="#ffffff" />
      <directionalLight position={[-10, 10, -5]} intensity={1.2} color="#93c5fd" />
      <pointLight position={[0, -5, 5]} intensity={0.8} color="#f97316" />
      
      <PESTerrain />
      <JablonskiDiagram />
      <PolymerMelt />
      <IonLattice />
    </>
  )
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

        {/* Dynamic Views over the Canvas */}
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
          <Canvas camera={{ position: [0, 2, 10], fov: 45 }}>
            <Suspense fallback={null}>
              <ScrollControls pages={6} damping={0.2}>
                <Scene />
                <Scroll html style={{ width: '100%' }}>
                  <HeroSection />
                  <SectionsContainer />
                </Scroll>
              </ScrollControls>
            </Suspense>
          </Canvas>
        )}

      </main>
    </ErrorBoundary>
  )
}

export default App
