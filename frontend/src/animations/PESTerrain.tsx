import { useRef, useMemo, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

// Terrain elevation function (Slower movement will be handled by passing slower time)
const getElevation = (x: number, z: number, time: number) => {
  const wave1 = Math.sin(x * 0.55 + time * 0.1) * Math.cos(z * 0.55 + time * 0.08) * 1.5;
  const wave2 = Math.sin(x * 0.30 - time * 0.05) * 0.8;
  let elevation = wave1 + wave2;

  // Make mountains slightly higher on the left edge (-X direction)
  if (x < -5) {
    const leftRamp = Math.min((Math.abs(x) - 5) / 10, 1.2); 
    elevation *= (1.0 + leftRamp); // Amplify waves on the left
  }

  return elevation;
}

// Molecule Definitions (Figma aesthetic: larger radii, premium colors)
type AtomData = { id: string; color: string; radius: number; pos: [number, number, number]; isLeaving?: boolean }
type BondData = { source: number; target: number }
type MoleculeTemplate = { atoms: AtomData[]; bonds: BondData[] }

const MOLECULES: Record<string, MoleculeTemplate> = {
  CH4: {
    atoms: [
      { id: 'C', color: '#1e293b', radius: 0.45, pos: [0, 0, 0] },
      { id: 'H1', color: '#ffffff', radius: 0.28, pos: [0.65, 0.65, 0.65] },
      { id: 'H2', color: '#ffffff', radius: 0.28, pos: [-0.65, -0.65, 0.65] },
      { id: 'H3', color: '#ffffff', radius: 0.28, pos: [-0.65, 0.65, -0.65] },
      { id: 'H4', color: '#ffffff', radius: 0.28, pos: [0.65, -0.65, -0.65], isLeaving: true }, 
    ],
    bonds: [{ source: 0, target: 1 }, { source: 0, target: 2 }, { source: 0, target: 3 }, { source: 0, target: 4 }]
  },
  NH3: {
    atoms: [
      { id: 'N', color: '#2563eb', radius: 0.42, pos: [0, 0.2, 0] },
      { id: 'H1', color: '#ffffff', radius: 0.28, pos: [0.65, -0.3, 0.4] },
      { id: 'H2', color: '#ffffff', radius: 0.28, pos: [-0.65, -0.3, 0.4] },
      { id: 'H3', color: '#ffffff', radius: 0.28, pos: [0, -0.3, -0.7], isLeaving: true },
    ],
    bonds: [{ source: 0, target: 1 }, { source: 0, target: 2 }, { source: 0, target: 3 }]
  },
  H2O: {
    atoms: [
      { id: 'O', color: '#ef4444', radius: 0.35, pos: [0, 0.2, 0] },
      { id: 'H1', color: '#f8fafc', radius: 0.25, pos: [0.6, -0.4, 0] },
      { id: 'H2', color: '#f8fafc', radius: 0.25, pos: [-0.6, -0.4, 0], isLeaving: true }, 
    ],
    bonds: [{ source: 0, target: 1 }, { source: 0, target: 2 }]
  },
  CH2O: {
    atoms: [
      { id: 'C', color: '#334155', radius: 0.4, pos: [0, 0, 0] },
      { id: 'O', color: '#ef4444', radius: 0.35, pos: [0, 0.7, 0] },
      { id: 'H1', color: '#f8fafc', radius: 0.25, pos: [0.6, -0.5, 0] },
      { id: 'H2', color: '#f8fafc', radius: 0.25, pos: [-0.6, -0.5, 0], isLeaving: true }, 
    ],
    bonds: [{ source: 0, target: 1 }, { source: 0, target: 2 }, { source: 0, target: 3 }]
  }
}

function DynamicMolecule({ template, center, phase, radius, speed }: { template: MoleculeTemplate, center: [number, number], phase: number, radius: number, speed: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const atomRefs = useRef<THREE.Mesh[]>([])
  const bondRefs = useRef<THREE.Mesh[]>([])

  const atomPositions = useMemo(() => template.atoms.map(a => new THREE.Vector3(...a.pos)), [template])
  const currentPositions = useMemo(() => template.atoms.map(() => new THREE.Vector3()), [template])
  
  const bondGeo = useMemo(() => new THREE.CylinderGeometry(0.08, 0.08, 1, 16), [])
  const bondMat = useMemo(() => new THREE.MeshPhysicalMaterial({ 
    color: '#94a3b8', 
    roughness: 0.2, 
    metalness: 0.3,
    clearcoat: 0.5 
  }), [])

  const upAxis = useMemo(() => new THREE.Vector3(0, 1, 0), [])

  useFrame(({ clock }) => {
    if (!groupRef.current) return
    // SLOWER TIME for the elevation calculation
    const t = clock.getElapsedTime() * 0.4 
    
    // Spread molecules out using the `center` prop
    const molX = center[0] + Math.sin(t * speed + phase) * radius
    const molZ = center[1] + Math.cos(t * speed * 1.2 + phase) * (radius * 0.8)
    const molY = getElevation(molX, molZ, t)
    
    groupRef.current.position.set(molX, molY + 0.8, molZ)
    // Cap heat so molecules on the high left mountains don't overstretch
    const heat = Math.min(Math.max(0, molY * 1.0), 2.5)
    
    groupRef.current.rotation.x = t * 0.2 + phase
    groupRef.current.rotation.y = t * 0.3 + phase
    groupRef.current.rotation.z = Math.sin(t) * 0.2

    const stretch = Math.max(0, heat - 0.5) * 1.5

    template.atoms.forEach((atom, i) => {
        const basePos = atomPositions[i]
        const currentPos = currentPositions[i]
        
        const jitterX = Math.sin(t * 15 + i * 1.2) * (0.01 + heat * 0.03)
        const jitterY = Math.cos(t * 14 + i * 2.1) * (0.01 + heat * 0.03)
        const jitterZ = Math.sin(t * 16 + i * 0.5) * (0.01 + heat * 0.03)

        currentPos.copy(basePos)
        currentPos.x += jitterX
        currentPos.y += jitterY
        currentPos.z += jitterZ

        if (atom.isLeaving) {
            const pullDir = basePos.clone().normalize()
            currentPos.add(pullDir.multiplyScalar(stretch))
        }

        if (atomRefs.current[i]) {
            atomRefs.current[i].position.copy(currentPos)
        }
    })

    template.bonds.forEach((bond, i) => {
        const bondMesh = bondRefs.current[i]
        if (!bondMesh) return

        const posA = currentPositions[bond.source]
        const posB = currentPositions[bond.target]
        const dist = posA.distanceTo(posB)

        const isLeavingBond = template.atoms[bond.target].isLeaving || template.atoms[bond.source].isLeaving
        if (isLeavingBond && dist > 1.8) {
            bondMesh.scale.set(0.001, 0.001, 0.001) 
            return
        }

        const midPoint = posA.clone().lerp(posB, 0.5)
        bondMesh.position.copy(midPoint)
        
        const direction = posB.clone().sub(posA).normalize()
        bondMesh.quaternion.setFromUnitVectors(upAxis, direction)
        
        const thickness = isLeavingBond ? Math.max(0.2, 1.0 - (dist - 1.0)) : 1.0
        bondMesh.scale.set(thickness, dist, thickness)
    })
  })

  return (
    <group ref={groupRef}>
      {template.atoms.map((atom, i) => (
        <mesh 
          key={`atom-${i}`}
          ref={el => { if(el) atomRefs.current[i] = el }}
        >
          <sphereGeometry args={[atom.radius, 32, 32]} />
          <meshPhysicalMaterial 
            color={atom.color} 
            roughness={0.1} 
            metalness={0.2} 
            clearcoat={1.0} 
          />
        </mesh>
      ))}
      {template.bonds.map((_, i) => (
        <mesh 
          key={`bond-${i}`}
          ref={el => { if(el) bondRefs.current[i] = el }}
          geometry={bondGeo} 
          material={bondMat} 
        />
      ))}
    </group>
  )
}

export default function PESTerrain() {
  const meshRef = useRef<THREE.Mesh>(null)
  const groupRef = useRef<THREE.Group>(null)
  const frameCount = useRef(0)
  
  // Grid sized for card header
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(26, 26, 70, 70)
    geo.rotateX(-Math.PI / 2)
    
    const count = geo.attributes.position.count
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
    
    return geo
  }, [])

  useEffect(() => {
    return () => {
      geometry.dispose()
    }
  }, [geometry])

  // Lighter colors for peak and valley (Orange-500 and Blue-500)
  const colorValley = useMemo(() => new THREE.Color('#f97316'), []) 
  const colorPeak = useMemo(() => new THREE.Color('#3b82f6'), []) 
  const tempColor = useMemo(() => new THREE.Color(), [])
  const tempVertex = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock }) => {
    // Smooth time for terrain waving
    const t = clock.getElapsedTime() * 0.4
    
    if (groupRef.current) {
      groupRef.current.visible = true
      groupRef.current.position.set(0, -1.8, -2)
      groupRef.current.rotation.set(-0.25, 0, 0)
    }

    const positionAttribute = geometry.attributes.position
    const colorAttribute = geometry.attributes.color
    
    for (let i = 0; i < positionAttribute.count; i++) {
      tempVertex.fromBufferAttribute(positionAttribute, i)
      
      const y = getElevation(tempVertex.x, tempVertex.z, t)
      positionAttribute.setY(i, y)
      
      // Calculate Gradient: Top = Blue, Valley = Orange
      const factor = Math.min(Math.max((y + 1.2) / 3.0, 0), 1)
      tempColor.lerpColors(colorValley, colorPeak, factor)
      
      colorAttribute.setXYZ(i, tempColor.r, tempColor.g, tempColor.b)
    }
    
    positionAttribute.needsUpdate = true
    colorAttribute.needsUpdate = true

    frameCount.current++
    if (frameCount.current % 2 === 0) {
      geometry.computeVertexNormals()
    }

    if (meshRef.current?.material) {
      (meshRef.current.material as THREE.MeshPhysicalMaterial).opacity = 0.85
    }
  })

  return (
    <group ref={groupRef} position={[0, -1.8, -2]} rotation={[-0.25, 0, 0]}>
      <mesh ref={meshRef} geometry={geometry}>
        <meshPhysicalMaterial 
          vertexColors={true}
          color="#ffffff"
          roughness={0.7}
          metalness={0.0}
          clearcoat={0.1}
          transparent={true}
          opacity={0.85}
          side={THREE.DoubleSide}
        />
      </mesh>
      
      <mesh geometry={geometry}>
        <meshBasicMaterial 
          color="#ffffff" 
          wireframe={true} 
          transparent={true} 
          opacity={0.15} 
        />
      </mesh>

      {/* Dynamic molecules visible within card frustum */}
      <DynamicMolecule template={MOLECULES.CH4} center={[-6, -4]} phase={0} radius={3.5} speed={0.8} />
      <DynamicMolecule template={MOLECULES.NH3} center={[6, -4]} phase={Math.PI * 0.6} radius={3.5} speed={0.6} />
      <DynamicMolecule template={MOLECULES.H2O} center={[-4, 3]} phase={Math.PI * 1.2} radius={3} speed={0.9} />
      <DynamicMolecule template={MOLECULES.CH2O} center={[4, 3]} phase={Math.PI * 1.7} radius={3.5} speed={0.5} />
      <DynamicMolecule template={MOLECULES.H2O} center={[0, -0.5]} phase={Math.PI * 0.3} radius={2} speed={1.1} />
    </group>
  )
}
