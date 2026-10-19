import { useRef, useMemo } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useScroll } from '@react-three/drei'
import * as THREE from 'three'

const NUM_CHAINS = 15
const BEADS_PER_CHAIN = 35
const TOTAL_BEADS = NUM_CHAINS * BEADS_PER_CHAIN

export default function PolymerMelt() {
  const groupRef = useRef<THREE.Group>(null)
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const lineGeoRef = useRef<THREE.BufferGeometry>(null)
  const lineMatRef = useRef<THREE.LineBasicMaterial>(null)
  const scroll = useScroll()
  
  // Dynamically fetch the user's screen dimensions to calculate perfect physical boundaries
  const { viewport } = useThree()

  // Precompute relaxed and stretched states, and chain physics metadata
  // We add viewport.width to dependencies so it recalculates perfect bounds on extreme window resizes
  const { relaxed, stretched, baseIndices, chainData } = useMemo(() => {
    const rel = new Float32Array(TOTAL_BEADS * 3)
    const str = new Float32Array(TOTAL_BEADS * 3)

    // Mathematically calculate the absolute left edge of the screen at the group's depth (Z = -5)
    // Camera is at Z = 10. Distance = 15. Standard z=0 distance = 10.
    const frustumScale = 15 / 10 
    const planeWidth = viewport.width * frustumScale
    
    // The absolute left edge of the monitor. We add a +0.5 safety margin so it doesn't touch the bezel.
    const absoluteLeftEdge = -(planeWidth / 2) + 0.5 
    
    // The group itself is shifted to X = -4.5. Calculate the relative local X for the left edge.
    const maxRelativeLeft = absoluteLeftEdge - (-4.5)
    
    // The text card starts on the right half of the screen. Max absolute X = 0.0.
    const maxRelativeRight = 0.0 - (-4.5) // Which is exactly +4.5

    const ind = new Uint16Array(NUM_CHAINS * (BEADS_PER_CHAIN - 1) * 2)
    const data = []

    let indexPtr = 0

    for (let c = 0; c < NUM_CHAINS; c++) {
      // Restrict Z-depth variation slightly to prevent wide camera frustum clipping differences
      const yBase = (Math.random() - 0.5) * 8
      const zBase = (Math.random() - 0.5) * 3
      
      let currRel = new THREE.Vector3(0, yBase, zBase)
      
      // Scientifically accurate: Assign a unique weak point (scission locus) for each chain
      data.push({
        breakBead: Math.floor(BEADS_PER_CHAIN * (0.3 + 0.4 * Math.random())), // Breaks near the middle
      })
      
      // PERFECTION: Start exactly at the screen's left edge, and stretch exactly to the center!
      const startX = maxRelativeLeft + Math.random() * 1.0 
      const endX = maxRelativeRight - Math.random() * 3.0 
      const stretchSpan = endX - startX

      for (let b = 0; b < BEADS_PER_CHAIN; b++) {
        const i = c * BEADS_PER_CHAIN + b
        
        if (b > 0) {
           const dir = new THREE.Vector3(
             Math.random() - 0.5, 
             Math.random() - 0.5, 
             Math.random() - 0.5
           ).normalize().multiplyScalar(0.7)
           currRel.add(dir)
        }
        
        rel[i * 3] = currRel.x
        rel[i * 3 + 1] = currRel.y
        rel[i * 3 + 2] = currRel.z
        
        const noiseY = (Math.random() - 0.5) * 0.3
        const noiseZ = (Math.random() - 0.5) * 0.3
        str[i * 3] = startX + b * (stretchSpan / (BEADS_PER_CHAIN - 1))
        str[i * 3 + 1] = yBase + noiseY
        str[i * 3 + 2] = zBase + noiseZ

        if (b < BEADS_PER_CHAIN - 1) {
          ind[indexPtr++] = i
          ind[indexPtr++] = i + 1
        }
      }
    }
    return { relaxed: rel, stretched: str, baseIndices: ind, chainData: data }
  }, [viewport.width])

  const linePositions = useMemo(() => new Float32Array(TOTAL_BEADS * 3), [])
  const activeIndices = useMemo(() => new Uint16Array(baseIndices.length), [baseIndices])
  const dummy = useMemo(() => new THREE.Object3D(), [])
  
  const colorBlue = useMemo(() => new THREE.Color('#3b82f6'), [])
  const colorRed = useMemo(() => new THREE.Color('#ef4444'), [])
  const tempColor = useMemo(() => new THREE.Color(), [])

  useFrame(({ clock }) => {
    const offset = scroll.offset
    const distance = Math.abs(offset - 0.60)
    const fadeOpacity = Math.max(0, (1 - distance * 2.5) * 1.0)
    const isVisible = fadeOpacity > 0.01

    if (groupRef.current) {
        groupRef.current.visible = isVisible
        const pageOffset = (offset - 0.60) / 0.20
        // Shifted vertically up (-1.5) to balance text
        groupRef.current.position.y = -1.5 + (pageOffset * 25)
    }

    if (!isVisible || !meshRef.current || !lineGeoRef.current) return

    // Global strain cycle (1.3 seconds mapped)
    // 0.0 -> 0.8 : Pulling phase (elastic stretching)
    // 0.8 -> 1.0 : Holding phase (all chains stay together in maximum stretch state)
    // 1.0 -> 1.1 : Snapping! (chain scission and entropic recoil apart)
    // 1.1 -> 1.3 : Healing/Reset (halves smoothly drift back together)
    const cycle = (clock.getElapsedTime() * 0.5) % 1.3 
    
    // Copy base index geometry (assume fully connected)
    activeIndices.set(baseIndices)

    for (let c = 0; c < NUM_CHAINS; c++) {
      const chain = chainData[c]
      
      const isBroken = cycle >= 1.0 // Stays broken throughout the reset phase
      const isResetting = cycle >= 1.1

      let effectiveStrain = 0
      let recoilOffset = 0 // Entropic recoil shifts broken halves apart
      let snapWobble = 0   // Whiplash oscillation

      if (isResetting) {
        effectiveStrain = 0
        // Smoothly drift the two broken halves back together over 0.2 seconds
        const resetProgress = (cycle - 1.1) / 0.2 
        const ease = 0.5 - 0.5 * Math.cos(resetProgress * Math.PI)
        recoilOffset = 5.0 * (1.0 - ease)
      } else if (isBroken) {
        const timeSinceBreak = cycle - 1.0
        
        // SNAPPING DRIFT: Instead of a static massive separation, they snap apart and continue drifting outwards
        const driftProgress = timeSinceBreak * 10.0 // goes 0.0 to 1.0 over the 0.1s broken phase
        const driftEase = 1.0 - Math.pow(1.0 - driftProgress, 3) // ease-out cubic for realistic momentum
        recoilOffset = 1.0 + (driftEase * 4.0) // drifts from 1.0 apart to 5.0 apart
        // Ultra-rapid collapse of the stretch (0.025 seconds instead of 0.1s)
        const recoil = Math.max(0, 1.0 - timeSinceBreak * 40.0) 
        effectiveStrain = recoil
        
        // Violent whiplash shaking that fades over the 0.1s broken phase
        snapWobble = Math.max(0, 1.0 - timeSinceBreak * 10.0) * 2.0 
      } else {
        // Elastic pulling and holding phase
        effectiveStrain = Math.min(1.0, cycle / 0.8)
      }

      for (let b = 0; b < BEADS_PER_CHAIN; b++) {
        const i = c * BEADS_PER_CHAIN + b

        // Break the covalent bond by severing the LineSegment geometry
        if (isBroken && b === chain.breakBead) {
          const idxOffset = c * (BEADS_PER_CHAIN - 1) * 2 + b * 2
          activeIndices[idxOffset] = i
          activeIndices[idxOffset + 1] = i // Line connects to itself (invisible)
        }

        // Apply physical recoil displacement depending on which side of the break this monomer is on
        const sideShift = isBroken || isResetting ? (b <= chain.breakBead ? -recoilOffset : recoilOffset) : 0

        // Calculate whiplash physics (only active immediately after snapping)
        let whipY = 0
        let whipZ = 0
        if (snapWobble > 0) {
           whipY = Math.sin(b * 123.4 + cycle * 200) * snapWobble
           whipZ = Math.cos(b * 321.4 + cycle * 200) * snapWobble
        }

        const x = THREE.MathUtils.lerp(relaxed[i * 3] + sideShift, stretched[i * 3], effectiveStrain)
        const y = THREE.MathUtils.lerp(relaxed[i * 3 + 1], stretched[i * 3 + 1], effectiveStrain) + whipY
        const z = THREE.MathUtils.lerp(relaxed[i * 3 + 2], stretched[i * 3 + 2], effectiveStrain) + whipZ
        
        dummy.position.set(x, y, z)
        dummy.updateMatrix()
        meshRef.current.setMatrixAt(i, dummy.matrix)
        
        linePositions[i * 3] = x
        linePositions[i * 3 + 1] = y
        linePositions[i * 3 + 2] = z

        // Scientifically accurate tension distribution:
        // The chain remains almost entirely Blue, except right at the specific 'weak point' (breakBead).
        // As strain increases, the weak point gradually glows red until it snaps.
        const distFromBreak = Math.abs(b - chain.breakBead)
        // Tension sharply drops off (only affecting ~4 beads away from the break point)
        const localStress = Math.max(0, 1.0 - distFromBreak / 4.0) 
        
        // Gentle quadratic fade so the red color transitions in smoothly as it stretches
        const burnFactor = Math.pow(effectiveStrain, 2) 
        
        const tension = isBroken ? 0 : burnFactor * localStress
        
        tempColor.copy(colorBlue).lerp(colorRed, tension)
        meshRef.current.setColorAt(i, tempColor)
      }
    }

    meshRef.current.instanceMatrix.needsUpdate = true
    if (meshRef.current.instanceColor) {
      meshRef.current.instanceColor.needsUpdate = true
    }
    
    if (lineGeoRef.current) {
      const posAttr = lineGeoRef.current.getAttribute('position') as THREE.BufferAttribute | undefined
      if (posAttr && posAttr.array === linePositions) {
        posAttr.needsUpdate = true
      } else {
        lineGeoRef.current.setAttribute('position', new THREE.BufferAttribute(linePositions, 3))
      }
      
      const indexAttr = lineGeoRef.current.getIndex()
      if (indexAttr && indexAttr.array.length === activeIndices.length) {
        (indexAttr.array as Uint16Array).set(activeIndices)
        indexAttr.needsUpdate = true
      } else {
        lineGeoRef.current.setIndex(new THREE.BufferAttribute(activeIndices, 1))
      }
    }
    
    if (meshRef.current.material) {
        (meshRef.current.material as THREE.Material).opacity = fadeOpacity
    }
    if (lineMatRef.current) {
        lineMatRef.current.opacity = fadeOpacity * 0.3
    }
  })

  return (
    // Anchored at X = -4.5 (left side) to perfectly balance the right text card
    <group ref={groupRef} position={[-4.5, -1.5, -5]} visible={false}>
      
      {/* Dynamic Polymer Bonds */}
      <lineSegments>
        <bufferGeometry ref={lineGeoRef}>
          {/* @ts-expect-error */}
          <bufferAttribute 
            attach="index" 
            array={baseIndices} 
            itemSize={1} 
            count={baseIndices.length} 
          />
        </bufferGeometry>
        <lineBasicMaterial 
          ref={lineMatRef} 
          color="#94a3b8" 
          transparent 
          opacity={0} 
        />
      </lineSegments>

      {/* Polymer Monomers (Beads) */}
      <instancedMesh 
        ref={meshRef} 
        args={[undefined, undefined, TOTAL_BEADS]}
      >
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshPhysicalMaterial 
            color="#ffffff"       
            roughness={0.1}
            transmission={0.8}    
            thickness={1.5}
            clearcoat={1.0}
            transparent={true}
            opacity={0}
        />
      </instancedMesh>
      
    </group>
  )
}
