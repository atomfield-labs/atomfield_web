import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { useScroll, Text, Line } from '@react-three/drei'
import * as THREE from 'three'

type State = 'S0' | 'S1' | 'T1'

interface Particle {
  state: State
  pos: THREE.Vector3
  timer: number
}

const PARTICLE_COUNT = 5

// Platform Y levels
const Y_S0 = -3.5
const Y_T1 = 2.0
const Y_S1 = 3.5

// Platform X bounds
const S0_X = [-4.0, 4.0]
const S1_X = [-4.0, -0.5]
const T1_X = [0.5, 4.0]

// Deterministic slotting prevents any overlaps
const getSlotX = (bounds: number[], i: number) => {
  const padding = 0.4
  const start = bounds[0] + padding
  const end = bounds[1] - padding
  if (PARTICLE_COUNT <= 1) return (start + end) / 2
  return start + (i / (PARTICLE_COUNT - 1)) * (end - start)
}

// Fixed Z perfectly in front of lines (Z=0). Prevents perspective size warping.
const FIXED_Z = 0.5

// Helper to pick a discrete vibrational level within a band
const pickLevel = (baseY: number, numLevels: number) => {
  const level = Math.floor(Math.random() * numLevels)
  return baseY + level * 0.15
}

interface EnergyBandProps {
  baseY: number
  minX: number
  maxX: number
  levels: number
  color: string
}

const EnergyBand = ({ baseY, minX, maxX, levels, color }: EnergyBandProps) => {
  return (
    <group>
      {Array.from({ length: levels }).map((_, i) => (
        <Line 
          key={i} 
          points={[[minX, baseY + i * 0.15, 0], [maxX, baseY + i * 0.15, 0]]} 
          color={color} 
          lineWidth={3} 
          transparent 
        />
      ))}
    </group>
  )
}

export default function JablonskiDiagram() {
  const groupRef = useRef<THREE.Group>(null)
  const instancedMeshRef = useRef<THREE.InstancedMesh>(null)
  const scroll = useScroll()

  // Initialize 5 Electron Clouds on discrete levels
  const particles = useMemo<Particle[]>(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      state: 'S0',
      pos: new THREE.Vector3(getSlotX(S0_X, i), pickLevel(Y_S0, 8), FIXED_Z),
      timer: Math.random() * 3.0
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])
  
  // Colors for discrete states
  const colorGreen = useMemo(() => new THREE.Color('#22c55e'), []) // Green-500
  const colorYellow = useMemo(() => new THREE.Color('#eab308'), []) // Yellow-500

  useFrame((_, delta) => {
    const offset = scroll.offset
    const distance = Math.abs(offset - 0.40)
    
    // Transparency multiplier (widened to crossfade with other sections)
    const fadeOpacity = Math.max(0, (1 - distance * 2.5) * 0.8) 
    const isVisible = fadeOpacity > 0.01

    if (groupRef.current) {
      groupRef.current.visible = isVisible
      const pageOffset = (offset - 0.40) / 0.20
      groupRef.current.position.y = -1.5 + (pageOffset * 25)
    }

    if (!isVisible || !instancedMeshRef.current) return

    particles.forEach((p, i) => {
      // Very soft jitter within the discrete level (only on X/Y so Z stays fixed)
      const jitterX = Math.sin(Date.now() * 0.001 + i) * 0.01
      
      switch (p.state) {
        case 'S0':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S1'
            p.pos.set(getSlotX(S1_X, i), pickLevel(Y_S1, 5), FIXED_Z)
            p.timer = 0.5 + Math.random() * 1.0 
          }
          break

        case 'S1':
          p.timer -= delta
          if (p.timer <= 0) {
            if (i % 2 === 0) {
              p.state = 'S0'
              p.pos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 8), FIXED_Z)
              p.timer = 1.5 + Math.random() * 2.0
            } else {
              p.state = 'T1'
              p.pos.set(getSlotX(T1_X, i), pickLevel(Y_T1, 4), FIXED_Z)
              p.timer = 4.0 + Math.random() * 4.0 
            }
          }
          break

        case 'T1':
          p.timer -= delta
          if (p.timer <= 0) {
            p.state = 'S0'
            p.pos.set(getSlotX(S0_X, i), pickLevel(Y_S0, 8), FIXED_Z)
            p.timer = 1.5 + Math.random() * 2.0
          }
          break
      }

      dummy.position.set(p.pos.x + jitterX, p.pos.y, FIXED_Z)
      dummy.scale.setScalar(0.4) 
      dummy.updateMatrix()
      instancedMeshRef.current!.setMatrixAt(i, dummy.matrix)
      
      // Permanently color electrons based on their pathway destiny (even = Fluo/Green, odd = Phos/Yellow)
      const isPhosphorescent = i % 2 !== 0
      instancedMeshRef.current!.setColorAt(i, isPhosphorescent ? colorYellow : colorGreen)
    })

    instancedMeshRef.current!.instanceMatrix.needsUpdate = true
    if (instancedMeshRef.current!.instanceColor) {
      instancedMeshRef.current!.instanceColor.needsUpdate = true
    }

    // Dynamically match transparency to the PES style (Electrons 0.8, Bands 0.15)
    if (instancedMeshRef.current!.material) {
        (instancedMeshRef.current!.material as THREE.Material).opacity = fadeOpacity
    }

    if (groupRef.current) {
      groupRef.current.children.forEach((child: any) => {
        child.traverse((obj: any) => {
            if (obj.material && obj.material.opacity !== undefined && obj.type === 'Line') {
                obj.material.opacity = fadeOpacity * 0.15 
            }
        })
      })
    }
  })

  const textMaterial = useMemo(() => new THREE.MeshBasicMaterial({
    color: '#64748b', 
    transparent: true,
    opacity: 0.8
  }), [])

  // Shifted group back to a balanced Y position (-1.5) now that S0 is vastly lower
  return (
    <group ref={groupRef} position={[6.0, -1.5, -6]} rotation={[0, 0, 0]} visible={false}>
      
      {/* S0: Ground State Bands */}
      <EnergyBand baseY={Y_S0} minX={S0_X[0]} maxX={S0_X[1]} levels={8} color="#94a3b8" />
      <Text position={[S0_X[0] - 0.5, Y_S0, 0]} fontSize={0.5} material={textMaterial} anchorX="right">
        S0
      </Text>

      {/* S1: Singlet Excited State Bands */}
      <EnergyBand baseY={Y_S1} minX={S1_X[0]} maxX={S1_X[1]} levels={5} color="#38bdf8" />
      <Text position={[S1_X[0] - 0.5, Y_S1, 0]} fontSize={0.5} material={textMaterial} anchorX="right">
        S1
      </Text>

      {/* T1: Triplet Excited State Bands */}
      <EnergyBand baseY={Y_T1} minX={T1_X[0]} maxX={T1_X[1]} levels={4} color="#f472b6" />
      <Text position={[T1_X[1] + 0.5, Y_T1, 0]} fontSize={0.5} material={textMaterial} anchorX="left">
        T1
      </Text>

      {/* Electron Clouds */}
      <instancedMesh 
        ref={instancedMeshRef} 
        args={[undefined, undefined, PARTICLE_COUNT]}
      >
        <sphereGeometry args={[1, 32, 32]} />
        {/* Base color white so instance colors apply fully */}
        <meshPhysicalMaterial 
            color="#ffffff"       
            roughness={0.1}
            transmission={0.8}    
            thickness={1.5}
            clearcoat={1.0}
            transparent={true}
        />
      </instancedMesh>
      
    </group>
  )
}
