import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const GRID = 4
const SPACING = 1.6
const TOTAL_ATOMS = GRID * GRID * GRID
const MAX_PATH = 8

export default function IonLattice() {
  const groupRef = useRef<THREE.Group>(null)
  const hostMeshRef = useRef<THREE.InstancedMesh>(null)
  const cloudMeshRef = useRef<THREE.InstancedMesh>(null)
  const ionMeshRef = useRef<THREE.Mesh>(null)
  const pathGeoRef = useRef<THREE.BufferGeometry>(null)
  

  // Base crystalline lattice structure
  const { atomPositions, dynamicAtomPositions, bondIndices } = useMemo(() => {
    const atoms = new Float32Array(TOTAL_ATOMS * 3)
    const dynamicAtoms = new Float32Array(TOTAL_ATOMS * 3)
    const bonds = []
    
    for (let x = 0; x < GRID; x++) {
      for (let y = 0; y < GRID; y++) {
        for (let z = 0; z < GRID; z++) {
          const i = x * GRID * GRID + y * GRID + z
          
          atoms[i * 3] = (x - (GRID - 1) / 2) * SPACING
          atoms[i * 3 + 1] = (y - (GRID - 1) / 2) * SPACING
          atoms[i * 3 + 2] = (z - (GRID - 1) / 2) * SPACING

          if (x < GRID - 1) bonds.push(i, i + GRID * GRID)
          if (y < GRID - 1) bonds.push(i, i + GRID)
          if (z < GRID - 1) bonds.push(i, i + 1)
        }
      }
    }
    
    dynamicAtoms.set(atoms)
    
    return { 
      atomPositions: atoms, 
      dynamicAtomPositions: dynamicAtoms,
      bondIndices: new Uint16Array(bonds) 
    }
  }, [])

  // Pre-create all geometry and materials to bypass any React wrapper bugs
  const hostGeo = useMemo(() => new THREE.SphereGeometry(0.2, 16, 16), [])
  const hostMat = useMemo(() => new THREE.MeshPhysicalMaterial({ 
      color: new THREE.Color("#7c3aed"), // Vibrant Violet
      roughness: 0.2, 
      metalness: 0.1,
      clearcoat: 0.8, 
      transparent: true,
      opacity: 0.95
  }), [])

  const cloudGeo = useMemo(() => new THREE.SphereGeometry(0.65, 16, 16), []) // Spread the clouds out
  const cloudMat = useMemo(() => new THREE.MeshBasicMaterial({ 
      color: new THREE.Color("#86efac"), // Ethereal pastel green
      transparent: true, 
      opacity: 0.22,
      depthWrite: false 
  }), [])

  const bondsMat = useMemo(() => new THREE.LineBasicMaterial({
      color: new THREE.Color("#a855f7"),
      transparent: true,
      opacity: 0.5
  }), [])

  // Statically initialized buffer geometry for bonds
  const bondsGeo = useMemo(() => {
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(dynamicAtomPositions, 3))
      geo.setIndex(new THREE.BufferAttribute(bondIndices, 1))
      return geo
  }, [dynamicAtomPositions, bondIndices])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  // Thermodynamics State Machine
  const state = useRef({
    isHopping: false,
    progress: 0,
    waitTime: 1.5,
    maxWaitTime: 1.5,
    currentSite: [1, 1, 1],
    targetSite: [1, 1, 1],
    pathHistory: [[1, 1, 1]]
  })

  const getSitePos = (site: number[]) => {
    return new THREE.Vector3(
      (site[0] - (GRID - 2) / 2) * SPACING,
      (site[1] - (GRID - 2) / 2) * SPACING,
      (site[2] - (GRID - 2) / 2) * SPACING
    )
  }

  const pathPositions = useMemo(() => new Float32Array(MAX_PATH * 3), [])

  useFrame(({ clock }, delta) => {
    if (groupRef.current) {
      groupRef.current.visible = true
      groupRef.current.position.set(0, 0, 0)
      groupRef.current.rotation.y = clock.getElapsedTime() * 0.12
      groupRef.current.rotation.x = clock.getElapsedTime() * 0.06
    }

    // Update statically allocated materials
    hostMat.opacity = 0.9
    cloudMat.opacity = 0.22
    bondsMat.opacity = 0.4

    const s = state.current
    
    // --- 1. LITHIUM ION THERMODYNAMICS ---
    if (s.isHopping) {
      s.progress += delta * 6.0 
      
      if (s.progress >= 1.0) {
        s.progress = 1.0
        s.isHopping = false
        s.maxWaitTime = 0.5 + Math.random() * 1.5 
        s.waitTime = s.maxWaitTime
        s.currentSite = [...s.targetSite]
      }
      
      const ease = 0.5 - 0.5 * Math.cos(s.progress * Math.PI)
      if (ionMeshRef.current) {
          ionMeshRef.current.position.lerpVectors(getSitePos(s.currentSite), getSitePos(s.targetSite), ease)
      }
    } else {
      s.waitTime -= delta
      
      const energyBuildUp = Math.max(0, 1.0 - (s.waitTime / s.maxWaitTime))
      const intensity = Math.pow(energyBuildUp, 4) * 0.35 + 0.03 
      
      const basePos = getSitePos(s.currentSite)
      if (ionMeshRef.current) {
          ionMeshRef.current.position.set(
              basePos.x + (Math.random() - 0.5) * intensity,
              basePos.y + (Math.random() - 0.5) * intensity,
              basePos.z + (Math.random() - 0.5) * intensity
          )
      }

      if (s.waitTime <= 0) {
        const axis = Math.floor(Math.random() * 3)
        const dir = Math.random() > 0.5 ? 1 : -1
        const nextSite = [...s.currentSite]
        
        nextSite[axis] += dir
        
        if (nextSite[axis] >= 0 && nextSite[axis] < GRID - 1) {
          s.targetSite = nextSite
          s.isHopping = true
          s.progress = 0
          
          s.pathHistory.push([...nextSite])
          if (s.pathHistory.length > MAX_PATH) {
            s.pathHistory.shift()
          }
        } else {
          s.waitTime = 0.1
        }
      }
    }

    if (ionMeshRef.current?.material) {
       (ionMeshRef.current.material as THREE.Material).opacity = 0.95
    }

    // --- 2. HOST LATTICE PHYSICS (Phonons, Polarons, & Electron Clouds) ---
    const time = clock.getElapsedTime()
    const ionPos = ionMeshRef.current ? ionMeshRef.current.position : new THREE.Vector3()

    if (hostMeshRef.current && cloudMeshRef.current) {
        for (let i = 0; i < TOTAL_ATOMS; i++) {
            const bx = atomPositions[i*3]
            const by = atomPositions[i*3+1]
            const bz = atomPositions[i*3+2]

            const phase = bx * 1.1 + by * 2.3 + bz * 3.7
            const vibX = Math.sin(time * 5.0 + phase) * 0.04
            const vibY = Math.cos(time * 6.0 + phase + 1.0) * 0.04
            const vibZ = Math.sin(time * 4.0 + phase + 2.0) * 0.04

            const dx = ionPos.x - bx
            const dy = ionPos.y - by
            const dz = ionPos.z - bz
            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz)

            let pullX = 0, pullY = 0, pullZ = 0
            if (dist < 2.8 && dist > 0.1) {
                const pullStrength = Math.pow(Math.max(0, 1.0 - dist / 2.8), 2) * 0.25
                pullX = (dx / dist) * pullStrength
                pullY = (dy / dist) * pullStrength
                pullZ = (dz / dist) * pullStrength
            }

            const finalX = bx + vibX + pullX
            const finalY = by + vibY + pullY
            const finalZ = bz + vibZ + pullZ

            dummy.position.set(finalX, finalY, finalZ)
            dummy.updateMatrix()
            hostMeshRef.current.setMatrixAt(i, dummy.matrix)

            dynamicAtomPositions[i*3] = finalX
            dynamicAtomPositions[i*3+1] = finalY
            dynamicAtomPositions[i*3+2] = finalZ

            const cloudX = bx + vibX + pullX * 2.5
            const cloudY = by + vibY + pullY * 2.5
            const cloudZ = bz + vibZ + pullZ * 2.5

            dummy.position.set(cloudX, cloudY, cloudZ)
            dummy.updateMatrix()
            cloudMeshRef.current.setMatrixAt(i, dummy.matrix)
        }
        
        hostMeshRef.current.instanceMatrix.needsUpdate = true
        cloudMeshRef.current.instanceMatrix.needsUpdate = true
        
        // Flag the bond line geometry for update
        if (bondsGeo.attributes.position) {
            bondsGeo.attributes.position.needsUpdate = true
        }
    }

    // --- 3. GLOWING DIFFUSION TRAIL ---
    if (pathGeoRef.current) {
        for (let i = 0; i < MAX_PATH; i++) {
            const site = s.pathHistory[i] || s.pathHistory[0] 
            const pos = getSitePos(site)
            pathPositions[i * 3] = pos.x
            pathPositions[i * 3 + 1] = pos.y
            pathPositions[i * 3 + 2] = pos.z
        }
        
        if (s.isHopping && s.pathHistory.length > 0 && ionMeshRef.current) {
            const tipIdx = (s.pathHistory.length - 1) * 3
            pathPositions[tipIdx] = ionMeshRef.current.position.x
            pathPositions[tipIdx + 1] = ionMeshRef.current.position.y
            pathPositions[tipIdx + 2] = ionMeshRef.current.position.z
        }
        
        if (!pathGeoRef.current.hasAttribute('position')) {
            pathGeoRef.current.setAttribute('position', new THREE.BufferAttribute(pathPositions, 3))
        } else {
            const positions = pathGeoRef.current.attributes.position as THREE.BufferAttribute
            for (let i = 0; i < MAX_PATH * 3; i++) {
                positions.array[i] = pathPositions[i]
            }
            positions.needsUpdate = true
        }
    }
  })

  return (
    <group ref={groupRef}>
      
      {/* Dynamic Lattice Bonds */}
      <lineSegments geometry={bondsGeo} material={bondsMat} />

      {/* Heavy Nuclei (Host Atoms) */}
      <instancedMesh ref={hostMeshRef} args={[hostGeo, hostMat, TOTAL_ATOMS]} />

      {/* Polarizable Electron Density Clouds */}
      <instancedMesh ref={cloudMeshRef} args={[cloudGeo, cloudMat, TOTAL_ATOMS]} />

      {/* Lithium Ion */}
      <mesh ref={ionMeshRef}>
        <sphereGeometry args={[0.3, 32, 32]} />
        <meshBasicMaterial color="#f59e0b" transparent /> 
      </mesh>

      {/* Diffusion Trail */}
      <line>
         <bufferGeometry ref={pathGeoRef} />
         <lineBasicMaterial color="#f59e0b" linewidth={2} transparent opacity={0.85} />
      </line>

    </group>
  )
}
