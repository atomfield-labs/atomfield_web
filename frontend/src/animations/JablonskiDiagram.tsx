import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

type State = 'S0' | 'S1' | 'T1'

interface Particle {
  state: State
  targetPos: THREE.Vector3
  displayPos: THREE.Vector3
  timer: number
  depthZ: number
}

const PARTICLE_COUNT = 6

// Platform Y levels
const Y_S0 = -1.6
const Y_T1 = 0.45
const Y_S1 = 1.35

// Platform X bounds - constrained so T1 stops well before right badges
const S0_X = [-2.2, 1.5]
const S1_X = [-2.2, -0.35]
const T1_X = [0.35, 1.5]

const SHELF_DEPTH = 1.1

const getSlotX = (bounds: number[], i: number) => {
  const padding = 0.2
  const start = bounds[0] + padding
  const end = bounds[1] - padding
  if (PARTICLE_COUNT <= 1) return (start + end) / 2
  return start + (i / (PARTICLE_COUNT - 1)) * (end - start)
}

const pickLevel = (baseY: number, numLevels: number) => {
  const level = Math.floor(Math.random() * numLevels)
  return baseY + level * 0.16
}

interface EnergyShelf3DProps {
  baseY: number
  minX: number
  maxX: number
  levels: number
  color: string
}

function EnergyShelf3D({ baseY, minX, maxX, levels, color }: EnergyShelf3DProps) {
  const D = SHELF_DEPTH
  const halfD = D / 2

  // 1. Sleek semi-transparent platform plane for the base ground vibrational state v=0
  const planeGeo = useMemo(() => new THREE.PlaneGeometry(maxX - minX, D), [maxX, minX, D])
  const planeMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.15,
    roughness: 0.3,
    metalness: 0.1,
    side: THREE.DoubleSide,
    depthWrite: false,
  }), [color])

  // 2. 3D Wireframe structure across all vibrational levels
  const wireframeGeo = useMemo(() => {
    const pts: THREE.Vector3[] = []

    // Base level (v=0) full perimeter frame + depth cross-ribs
    pts.push(new THREE.Vector3(minX, baseY, -halfD), new THREE.Vector3(maxX, baseY, -halfD))
    pts.push(new THREE.Vector3(maxX, baseY, -halfD), new THREE.Vector3(maxX, baseY, halfD))
    pts.push(new THREE.Vector3(maxX, baseY, halfD), new THREE.Vector3(minX, baseY, halfD))
    pts.push(new THREE.Vector3(minX, baseY, halfD), new THREE.Vector3(minX, baseY, -halfD))

    // Intermediate ribs along Z at 1/3 and 2/3
    const x1 = minX + (maxX - minX) * 0.33
    const x2 = minX + (maxX - minX) * 0.67
    pts.push(new THREE.Vector3(x1, baseY, -halfD), new THREE.Vector3(x1, baseY, halfD))
    pts.push(new THREE.Vector3(x2, baseY, -halfD), new THREE.Vector3(x2, baseY, halfD))

    // Higher vibrational levels v=1..levels-1 (rectangular frames with depth)
    for (let i = 1; i < levels; i++) {
      const y = baseY + i * 0.16
      pts.push(new THREE.Vector3(minX, y, halfD), new THREE.Vector3(maxX, y, halfD))
      pts.push(new THREE.Vector3(minX, y, -halfD), new THREE.Vector3(maxX, y, -halfD))
      pts.push(new THREE.Vector3(minX, y, -halfD), new THREE.Vector3(minX, y, halfD))
      pts.push(new THREE.Vector3(maxX, y, -halfD), new THREE.Vector3(maxX, y, halfD))
    }

    // Vertical corner support struts connecting the stack
    const topY = baseY + (levels - 1) * 0.16
    pts.push(new THREE.Vector3(minX, baseY, -halfD), new THREE.Vector3(minX, topY, -halfD))
    pts.push(new THREE.Vector3(minX, baseY, halfD), new THREE.Vector3(minX, topY, halfD))
    pts.push(new THREE.Vector3(maxX, baseY, -halfD), new THREE.Vector3(maxX, topY, -halfD))
    pts.push(new THREE.Vector3(maxX, baseY, halfD), new THREE.Vector3(maxX, topY, halfD))

    return new THREE.BufferGeometry().setFromPoints(pts)
  }, [baseY, minX, maxX, levels, halfD])

  const wireframeMat = useMemo(() => new THREE.LineBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.65,
  }), [color])

  return (
    <group>
      {/* 3D Platform Floor */}
      <mesh 
        position={[(minX + maxX) / 2, baseY, 0]} 
        rotation={[-Math.PI / 2, 0, 0]} 
        geometry={planeGeo} 
        material={planeMat} 
      />
      {/* 3D Wireframe Cage & Shelves */}
      <lineSegments geometry={wireframeGeo} material={wireframeMat} />
    </group>
  )
}

// 3D Quantum Transition Pathways (Absorption, ISC, Radiative Decay)
function TransitionPathways() {
  const geo = useMemo(() => {
    const pts: THREE.Vector3[] = []
    
    // 1. Excitation / Absorption pathway: S0 -> S1 (vertical dashed guide at X = -1.4)
    for (let y = Y_S0 + 0.1; y < Y_S1; y += 0.22) {
      pts.push(new THREE.Vector3(-1.4, y, 0), new THREE.Vector3(-1.4, Math.min(Y_S1, y + 0.11), 0))
    }

    // 2. Intersystem Crossing (ISC) pathway: S1 -> T1 (curved bridge from S1 right edge to T1 left edge)
    const pStart = new THREE.Vector3(-0.35, Y_S1, 0)
    const pEnd = new THREE.Vector3(0.35, Y_T1 + 0.32, 0)
    const steps = 10
    for (let k = 0; k < steps; k++) {
      const t1 = k / steps
      const t2 = (k + 0.6) / steps
      const y1 = THREE.MathUtils.lerp(pStart.y, pEnd.y, t1) + Math.sin(t1 * Math.PI) * 0.15
      const y2 = THREE.MathUtils.lerp(pStart.y, pEnd.y, t2) + Math.sin(t2 * Math.PI) * 0.15
      const x1 = THREE.MathUtils.lerp(pStart.x, pEnd.x, t1)
      const x2 = THREE.MathUtils.lerp(pStart.x, pEnd.x, t2)
      pts.push(new THREE.Vector3(x1, y1, 0), new THREE.Vector3(x2, y2, 0))
    }

    // 3. Phosphorescence decay pathway: T1 -> S0 (vertical dashed guide at X = 0.9)
    for (let y = Y_S0 + 0.1; y < Y_T1; y += 0.22) {
      pts.push(new THREE.Vector3(0.9, y, 0), new THREE.Vector3(0.9, Math.min(Y_T1, y + 0.11), 0))
    }

    return new THREE.BufferGeometry().setFromPoints(pts)
  }, [])

  const mat = useMemo(() => new THREE.LineBasicMaterial({
    color: '#94a3b8',
    transparent: true,
    opacity: 0.35,
  }), [])

  return <lineSegments geometry={geo} material={mat} />
}

export default function JablonskiDiagram() {
  const groupRef = useRef<THREE.Group>(null)
  const instancedMeshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => {
      const depthZ = -0.32 + ((i % 3) / 2) * 0.64 // Distributed across 3D shelf depth
      const initialPos = new THREE.Vector3(getSlotX(S0_X, i), pickLevel(Y_S0, 5), depthZ)
      return {
        state: 'S0',
        targetPos: initialPos.clone(),
        displayPos: initialPos.clone(),
        timer: 0.5 + Math.random() * 2.5,
        depthZ
      }
    })
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])
  
  // High quality 3D spherical geometry for excitons/electrons
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(0.18, 24, 24), [])
  const sphereMat = useMemo(() => new THREE.MeshPhysicalMaterial({ 
    color: '#ffffff',
    roughness: 0.25,
    metalness: 0.15,
    clearcoat: 0.85,
    clearcoatRoughness: 0.15,
    emissive: '#111827',
    emissiveIntensity: 0.15,
  }), [])

  const colorGreen = useMemo(() => new THREE.Color('#22c55e'), []) // Fluorescent singlet (emerald)
  const colorYellow = useMemo(() => new THREE.Color('#f59e0b'), []) // Phosphorescent triplet (amber)

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime()

    // Smooth 3D isometric breathing rotation
    if (groupRef.current) {
      groupRef.current.visible = true
      groupRef.current.position.set(0, 0, 0)
      groupRef.current.rotation.y = -0.28 + Math.sin(t * 0.35) * 0.04
      groupRef.current.rotation.x = 0.18 + Math.cos(t * 0.28) * 0.03
    }

    if (!instancedMeshRef.current) return

    particles.forEach((p, i) => {
      // Physical quantum transitions (Preserving original transition cycles & timers)
      switch (p.state) {
        case 'S0':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S1'
            p.targetPos.set(getSlotX(S1_X, i), pickLevel(Y_S1, 4), p.depthZ)
            p.timer = 0.8 + Math.random() * 1.0 
          }
          break

        case 'S1':
          p.timer -= delta
          if (p.timer <= 0) {
            if (i % 2 === 0) {
              // Direct radiative decay: Fluorescence S1 -> S0
              p.state = 'S0'
              p.targetPos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), p.depthZ)
              p.timer = 1.2 + Math.random() * 1.8
            } else {
              // Intersystem crossing: S1 -> T1
              p.state = 'T1'
              p.targetPos.set(getSlotX(T1_X, i), pickLevel(Y_T1, 3), p.depthZ)
              p.timer = 2.5 + Math.random() * 2.5 
            }
          }
          break

        case 'T1':
          p.timer -= delta
          if (p.timer <= 0) {
            // Radiative decay: Phosphorescence T1 -> S0
            p.state = 'S0'
            p.targetPos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), p.depthZ)
            p.timer = 1.2 + Math.random() * 1.8
          }
          break
      }

      // Smooth 3D interpolation towards target position during transitions
      p.displayPos.lerp(p.targetPos, Math.min(1, delta * 7.0))

      // Subtle 3D quantum zero-point vibration
      const jitterX = Math.sin(t * 2.2 + i * 1.3) * 0.02
      const jitterY = Math.cos(t * 2.7 + i * 1.1) * 0.015
      const jitterZ = Math.sin(t * 1.9 + i * 2.1) * 0.02

      dummy.position.set(
        p.displayPos.x + jitterX, 
        p.displayPos.y + jitterY, 
        p.displayPos.z + jitterZ
      )
      dummy.scale.setScalar(1.0) 
      dummy.updateMatrix()
      instancedMeshRef.current!.setMatrixAt(i, dummy.matrix)
      
      const isPhosphorescent = i % 2 !== 0
      instancedMeshRef.current!.setColorAt(i, isPhosphorescent ? colorYellow : colorGreen)
    })

    instancedMeshRef.current.instanceMatrix.needsUpdate = true
    if (instancedMeshRef.current.instanceColor) {
      instancedMeshRef.current.instanceColor.needsUpdate = true
    }
  })

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      {/* S0: Ground State 3D Energy Platform Stack */}
      <EnergyShelf3D baseY={Y_S0} minX={S0_X[0]} maxX={S0_X[1]} levels={5} color="#475569" />

      {/* S1: Singlet Excited State 3D Energy Platform Stack */}
      <EnergyShelf3D baseY={Y_S1} minX={S1_X[0]} maxX={S1_X[1]} levels={4} color="#0284c7" />

      {/* T1: Triplet Excited State 3D Energy Platform Stack (constrained to avoid right edge) */}
      <EnergyShelf3D baseY={Y_T1} minX={T1_X[0]} maxX={T1_X[1]} levels={3} color="#e11d48" />

      {/* 3D Quantum Transition Guides */}
      <TransitionPathways />

      {/* 3D Exciton / Electron Spheres */}
      <instancedMesh 
        ref={instancedMeshRef} 
        args={[sphereGeo, sphereMat, PARTICLE_COUNT]}
      />
    </group>
  )
}

