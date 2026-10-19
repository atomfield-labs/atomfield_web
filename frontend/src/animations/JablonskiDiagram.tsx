import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

type State = 'S0' | 'S1' | 'T1'

interface Particle {
  state: State
  targetPos: THREE.Vector3
  displayPos: THREE.Vector3
  timer: number
}

const PARTICLE_COUNT = 6

// Platform Y levels
const Y_S0 = -1.6
const Y_T1 = 0.45
const Y_S1 = 1.35

// Platform X bounds - lines represent the bands as earlier, with T1 stopping before badge
const S0_X = [-2.4, 1.4]
const S1_X = [-2.4, -0.35]
const T1_X = [0.35, 1.4]

const FIXED_Z = 0.25

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

interface EnergyBandProps {
  baseY: number
  minX: number
  maxX: number
  levels: number
  color: string
}

// Clean horizontal line bands as earlier
function EnergyBand({ baseY, minX, maxX, levels, color }: EnergyBandProps) {
  const geo = useMemo(() => {
    const pts: THREE.Vector3[] = []
    for (let i = 0; i < levels; i++) {
      const y = baseY + i * 0.16
      pts.push(new THREE.Vector3(minX, y, 0))
      pts.push(new THREE.Vector3(maxX, y, 0))
    }
    return new THREE.BufferGeometry().setFromPoints(pts)
  }, [baseY, minX, maxX, levels])

  const mat = useMemo(() => new THREE.LineBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.65
  }), [color])

  return <lineSegments geometry={geo} material={mat} />
}

export default function JablonskiDiagram() {
  const groupRef = useRef<THREE.Group>(null)
  const instancedMeshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => {
      const initialPos = new THREE.Vector3(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z)
      return {
        state: 'S0',
        targetPos: initialPos.clone(),
        displayPos: initialPos.clone(),
        timer: 0.5 + Math.random() * 2.5
      }
    })
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])
  
  // 3D Spheres for electron / exciton balls with physical lighting and specular highlights
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(0.2, 24, 24), [])
  const sphereMat = useMemo(() => new THREE.MeshPhysicalMaterial({ 
    color: '#ffffff',
    roughness: 0.2,
    metalness: 0.15,
    clearcoat: 0.9,
    clearcoatRoughness: 0.1,
    emissive: '#111827',
    emissiveIntensity: 0.15,
  }), [])

  const colorGreen = useMemo(() => new THREE.Color('#22c55e'), []) // Fluorescent singlet (emerald)
  const colorYellow = useMemo(() => new THREE.Color('#f59e0b'), []) // Phosphorescent triplet (amber)

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime()

    if (groupRef.current) {
      groupRef.current.visible = true
      groupRef.current.position.set(0, 0, 0)
    }

    if (!instancedMeshRef.current) return

    particles.forEach((p, i) => {
      switch (p.state) {
        case 'S0':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S1'
            p.targetPos.set(getSlotX(S1_X, i), pickLevel(Y_S1, 4), FIXED_Z)
            p.timer = 0.8 + Math.random() * 1.0 
          }
          break

        case 'S1':
          p.timer -= delta
          if (p.timer <= 0) {
            if (i % 2 === 0) {
              // Direct radiative decay: Fluorescence S1 -> S0
              p.state = 'S0'
              p.targetPos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z)
              p.timer = 1.2 + Math.random() * 1.8
            } else {
              // Intersystem crossing: S1 -> T1
              p.state = 'T1'
              p.targetPos.set(getSlotX(T1_X, i), pickLevel(Y_T1, 3), FIXED_Z)
              p.timer = 2.5 + Math.random() * 2.5 
            }
          }
          break

        case 'T1':
          p.timer -= delta
          if (p.timer <= 0) {
            // Radiative decay: Phosphorescence T1 -> S0
            p.state = 'S0'
            p.targetPos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z)
            p.timer = 1.2 + Math.random() * 1.8
          }
          break
      }

      // Smooth 3D interpolation towards target position during transitions
      p.displayPos.lerp(p.targetPos, Math.min(1, delta * 7.0))

      // Subtle 3D quantum zero-point vibration
      const jitterX = Math.sin(t * 2.2 + i * 1.3) * 0.02
      const jitterY = Math.cos(t * 2.7 + i * 1.1) * 0.015

      dummy.position.set(
        p.displayPos.x + jitterX, 
        p.displayPos.y + jitterY, 
        FIXED_Z
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
      {/* S0: Ground State Bands */}
      <EnergyBand baseY={Y_S0} minX={S0_X[0]} maxX={S0_X[1]} levels={5} color="#475569" />

      {/* S1: Singlet Excited State Bands */}
      <EnergyBand baseY={Y_S1} minX={S1_X[0]} maxX={S1_X[1]} levels={4} color="#0284c7" />

      {/* T1: Triplet Excited State Bands (stopping at 1.4 to avoid badge overlap) */}
      <EnergyBand baseY={Y_T1} minX={T1_X[0]} maxX={T1_X[1]} levels={3} color="#e11d48" />

      {/* 3D Exciton / Electron Spheres */}
      <instancedMesh 
        ref={instancedMeshRef} 
        args={[sphereGeo, sphereMat, PARTICLE_COUNT]}
      />
    </group>
  )
}
