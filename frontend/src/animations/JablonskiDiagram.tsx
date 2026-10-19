import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

type State = 'S0' | 'S1' | 'T1'

interface Particle {
  state: State
  pos: THREE.Vector3
  timer: number
}

const PARTICLE_COUNT = 6

// Platform Y levels
const Y_S0 = -1.6
const Y_T1 = 0.5
const Y_S1 = 1.5

// Platform X bounds
const S0_X = [-2.8, 2.8]
const S1_X = [-2.8, -0.4]
const T1_X = [0.4, 2.8]

const getSlotX = (bounds: number[], i: number) => {
  const padding = 0.3
  const start = bounds[0] + padding
  const end = bounds[1] - padding
  if (PARTICLE_COUNT <= 1) return (start + end) / 2
  return start + (i / (PARTICLE_COUNT - 1)) * (end - start)
}

const FIXED_Z = 0.2

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

function EnergyBand({ baseY, minX, maxX, levels, color }: EnergyBandProps) {
  const geo = useMemo(() => {
    const pts: THREE.Vector3[] = []
    for (let i = 0; i < levels; i++) {
      pts.push(new THREE.Vector3(minX, baseY + i * 0.16, 0))
      pts.push(new THREE.Vector3(maxX, baseY + i * 0.16, 0))
    }
    return new THREE.BufferGeometry().setFromPoints(pts)
  }, [baseY, minX, maxX, levels])

  const mat = useMemo(() => new THREE.LineBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.55
  }), [color])

  return <lineSegments geometry={geo} material={mat} />
}

export default function JablonskiDiagram() {
  const groupRef = useRef<THREE.Group>(null)
  const instancedMeshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      state: 'S0',
      pos: new THREE.Vector3(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z),
      timer: Math.random() * 3.0
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(0.22, 16, 16), [])
  const sphereMat = useMemo(() => new THREE.MeshBasicMaterial({ 
    color: '#ffffff',
    transparent: true,
    opacity: 0.95
  }), [])

  const colorGreen = useMemo(() => new THREE.Color('#16a34a'), []) // Fluorescent singlet
  const colorYellow = useMemo(() => new THREE.Color('#d97706'), []) // Phosphorescent triplet

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.visible = true
      groupRef.current.position.set(0, 0, 0)
    }

    if (!instancedMeshRef.current) return

    particles.forEach((p, i) => {
      const jitterX = Math.sin(Date.now() * 0.001 + i) * 0.02
      
      switch (p.state) {
        case 'S0':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S1'
            p.pos.set(getSlotX(S1_X, i), pickLevel(Y_S1, 4), FIXED_Z)
            p.timer = 0.6 + Math.random() * 1.0 
          }
          break

        case 'S1':
          p.timer -= delta
          if (p.timer <= 0) {
            if (i % 2 === 0) {
              p.state = 'S0'
              p.pos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z)
              p.timer = 1.2 + Math.random() * 1.8
            } else {
              p.state = 'T1'
              p.pos.set(getSlotX(T1_X, i), pickLevel(Y_T1, 3), FIXED_Z)
              p.timer = 2.5 + Math.random() * 2.5 
            }
          }
          break

        case 'T1':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S0'
            p.pos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 5), FIXED_Z)
            p.timer = 1.2 + Math.random() * 1.8
          }
          break
      }

      dummy.position.set(p.pos.x + jitterX, p.pos.y, FIXED_Z)
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
    <group ref={groupRef} position={[0, 0, 0]} rotation={[0, 0, 0]}>
      {/* S0: Ground State Bands */}
      <EnergyBand baseY={Y_S0} minX={S0_X[0]} maxX={S0_X[1]} levels={5} color="#475569" />

      {/* S1: Singlet Excited State Bands */}
      <EnergyBand baseY={Y_S1} minX={S1_X[0]} maxX={S1_X[1]} levels={4} color="#0284c7" />

      {/* T1: Triplet Excited State Bands */}
      <EnergyBand baseY={Y_T1} minX={T1_X[0]} maxX={T1_X[1]} levels={3} color="#e11d48" />

      {/* Electron Clouds */}
      <instancedMesh 
        ref={instancedMeshRef} 
        args={[sphereGeo, sphereMat, PARTICLE_COUNT]}
      />
    </group>
  )
}
