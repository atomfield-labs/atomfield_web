import { useState, useEffect, useRef } from 'react';

export default function PipelineFlowHero() {
  const [phase, setPhase] = useState<'building' | 'simulating'>('building');
  const [buildStep, setBuildStep] = useState<number>(0);
  const [activeNode, setActiveNode] = useState<number>(-1);
  const [simProgress, setSimProgress] = useState<number>(0);
  const [productsVisible, setProductsVisible] = useState<boolean>(false);

  // Path refs for exact bezier trajectory calculation
  const path1Ref = useRef<SVGPathElement>(null);
  const path2Ref = useRef<SVGPathElement>(null);
  const path3Ref = useRef<SVGPathElement>(null);
  const path4Ref = useRef<SVGPathElement>(null);
  const path5ARef = useRef<SVGPathElement>(null);
  const path5BRef = useRef<SVGPathElement>(null);
  const path5CRef = useRef<SVGPathElement>(null);

  // Molecule position on canvas
  const [molPos, setMolPos] = useState<{ x: number; y: number; angle: number }>({ x: 62.5, y: 43, angle: 0 });
  const [productParticles, setProductParticles] = useState<{
    a: { x: number; y: number };
    b: { x: number; y: number };
    c: { x: number; y: number };
  }>({
    a: { x: 165, y: 248 },
    b: { x: 165, y: 248 },
    c: { x: 165, y: 248 },
  });

  // 1. Creation sequence: Step 0 to 4 (Reactant through DFT Refinement only. Products appear later!)
  useEffect(() => {
    if (phase !== 'building') return;

    setProductsVisible(false);
    setActiveNode(-1);
    setSimProgress(0);

    const timer = setInterval(() => {
      setBuildStep((prev) => {
        if (prev >= 4) {
          clearInterval(timer);
          setTimeout(() => {
            setPhase('simulating');
          }, 350);
          return 4;
        }
        return prev + 1;
      });
    }, 450);

    return () => clearInterval(timer);
  }, [phase]);

  // 2. Molecule simulation loop & Restart on highlight
  useEffect(() => {
    if (phase !== 'simulating') return;

    let animId: number;
    let startTime: number | null = null;
    let restartTimer: ReturnType<typeof setTimeout> | null = null;
    const duration = 6000; // 6s to travel through pipeline

    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      setSimProgress(progress);

      if (progress < 0.18) {
        // Reactant -> travelling Path 1 to MLFF
        setActiveNode(0);
        const subP = progress / 0.18;
        if (path1Ref.current) {
          const len = path1Ref.current.getTotalLength();
          const pt = path1Ref.current.getPointAtLength(subP * len);
          setMolPos({ x: pt.x, y: pt.y, angle: subP * 360 });
        }
      } else if (progress < 0.38) {
        // MLFF Geom Opt -> travelling Path 2 to Reactive MD
        setActiveNode(1);
        const subP = (progress - 0.18) / 0.20;
        if (path2Ref.current) {
          const len = path2Ref.current.getTotalLength();
          const pt = path2Ref.current.getPointAtLength(subP * len);
          setMolPos({ x: pt.x, y: pt.y, angle: subP * 360 });
        }
      } else if (progress < 0.58) {
        // Reactive MD -> travelling Path 3 to Conformer Sampling
        setActiveNode(2);
        const subP = (progress - 0.38) / 0.20;
        if (path3Ref.current) {
          const len = path3Ref.current.getTotalLength();
          const pt = path3Ref.current.getPointAtLength(subP * len);
          setMolPos({ x: pt.x, y: pt.y, angle: subP * 360 });
        }
      } else if (progress < 0.76) {
        // Conformer Sampling -> travelling Path 4 to DFT Refinement
        setActiveNode(3);
        const subP = (progress - 0.58) / 0.18;
        if (path4Ref.current) {
          const len = path4Ref.current.getTotalLength();
          const pt = path4Ref.current.getPointAtLength(subP * len);
          setMolPos({ x: pt.x, y: pt.y, angle: subP * 360 });
        }
      } else if (progress < 0.86) {
        // Inside DFT Refinement (products still NOT visible)
        setActiveNode(4);
        setMolPos({ x: 100, y: 248, angle: 0 });
      } else {
        // MOLECULE LEAVES DFT REFINEMENT: Products appear now!
        setProductsVisible(true);
        const subP = (progress - 0.86) / 0.14;

        if (subP < 0.85) {
          setActiveNode(4);
        } else {
          // Molecule arrives at Product B -> HIGHEST PROBABLE HIGHLIGHTED!
          setActiveNode(5);
        }

        if (path5BRef.current) {
          const lenB = path5BRef.current.getTotalLength();
          const ptB = path5BRef.current.getPointAtLength(Math.min(subP, 1) * lenB);
          setMolPos({ x: ptB.x, y: ptB.y, angle: subP * 360 });
        }
        if (path5ARef.current && path5CRef.current) {
          const lenA = path5ARef.current.getTotalLength();
          const ptA = path5ARef.current.getPointAtLength(Math.min(subP, 1) * lenA);
          const lenC = path5CRef.current.getTotalLength();
          const ptC = path5CRef.current.getPointAtLength(Math.min(subP, 1) * lenC);
          setProductParticles({
            a: { x: ptA.x, y: ptA.y },
            b: { x: molPos.x, y: molPos.y },
            c: { x: ptC.x, y: ptC.y },
          });
        }
      }

      if (progress < 1) {
        animId = requestAnimationFrame(animate);
      } else {
        // High yield product is highlighted! Wait 1.8 seconds, then restart animation from scratch
        restartTimer = setTimeout(() => {
          setPhase('building');
          setBuildStep(0);
          setProductsVisible(false);
          setActiveNode(-1);
          setSimProgress(0);
        }, 1800);
      }
    };

    animId = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animId);
      if (restartTimer) clearTimeout(restartTimer);
    };
  }, [phase]);

  return (
    <div className="w-full relative select-none">
      <svg
        viewBox="0 0 580 340"
        className="w-full h-auto overflow-visible font-sans"
      >
        <defs>
          {/* Subtle Drop Shadow for pure nodes */}
          <filter id="node-shadow" x="-8%" y="-12%" width="120%" height="130%">
            <feDropShadow dx="0" dy="1.5" stdDeviation="2.5" floodColor="#0f172a" floodOpacity="0.06" />
          </filter>

          {/* Arrowhead markers */}
          <marker
            id="arr-orange"
            viewBox="0 0 10 10"
            refX="7"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#f97316" />
          </marker>

          <marker
            id="arr-slate"
            viewBox="0 0 10 10"
            refX="7"
            refY="5"
            markerWidth="4.5"
            markerHeight="4.5"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#94a3b8" />
          </marker>
        </defs>

        {/* ======================================================== */}
        {/* EDGES / ARROWS (Non-linear curved circuit) */}
        {/* ======================================================== */}

        {/* Edge 1: Reactant (110, 43) -> MLFF Geom Opt (180, 43) */}
        <path
          ref={path1Ref}
          d="M 110 43 L 180 43"
          fill="none"
          stroke={activeNode === 0 ? '#f97316' : '#cbd5e1'}
          strokeWidth={activeNode === 0 ? '2.5' : '1.5'}
          markerEnd={activeNode === 0 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={buildStep >= 1 ? 1 : 0.15}
          className="transition-colors duration-200"
        />

        {/* Edge 2: MLFF Geom Opt (315, 43) -> Reactive MD (380, 43) */}
        <path
          ref={path2Ref}
          d="M 315 43 L 380 43"
          fill="none"
          stroke={activeNode === 1 ? '#f97316' : '#cbd5e1'}
          strokeWidth={activeNode === 1 ? '2.5' : '1.5'}
          markerEnd={activeNode === 1 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={buildStep >= 2 ? 1 : 0.15}
          className="transition-colors duration-200"
        />

        {/* Edge 3: Reactive MD (437, 61) -> Conformer Sampling (395, 148) [Curved S-Loop] */}
        <path
          ref={path3Ref}
          d="M 437 61 C 437 110, 425 148, 395 148"
          fill="none"
          stroke={activeNode === 2 ? '#f97316' : '#cbd5e1'}
          strokeWidth={activeNode === 2 ? '2.5' : '1.5'}
          markerEnd={activeNode === 2 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={buildStep >= 3 ? 1 : 0.15}
          className="transition-colors duration-200"
        />

        {/* Edge 4: Conformer Sampling (250, 148) -> DFT Refinement (100, 230) [Curved Sweep] */}
        <path
          ref={path4Ref}
          d="M 250 148 C 160 148, 100 185, 100 230"
          fill="none"
          stroke={activeNode === 3 ? '#f97316' : '#cbd5e1'}
          strokeWidth={activeNode === 3 ? '2.5' : '1.5'}
          markerEnd={activeNode === 3 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={buildStep >= 4 ? 1 : 0.15}
          className="transition-colors duration-200"
        />

        {/* Edge 5A: DFT Refinement (165, 248) -> Product A (420, 195) */}
        {/* ONLY APPEARS WHEN MOLECULE LEAVES DFT REFINEMENT */}
        <path
          ref={path5ARef}
          d="M 165 248 C 275 248, 315 195, 420 195"
          fill="none"
          stroke={activeNode === 4 ? '#f97316' : '#cbd5e1'}
          strokeWidth="1.5"
          markerEnd={activeNode === 4 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={productsVisible ? 0.8 : 0}
          className="transition-opacity duration-300"
        />

        {/* Edge 5B: DFT Refinement (165, 248) -> Product B (Highest Probable) (390, 249) */}
        {/* ONLY APPEARS WHEN MOLECULE LEAVES DFT REFINEMENT */}
        <path
          ref={path5BRef}
          d="M 165 248 C 250 248, 310 249, 390 249"
          fill="none"
          stroke={activeNode === 5 ? '#f97316' : '#cbd5e1'}
          strokeWidth={activeNode === 5 ? '2.5' : '1.8'}
          markerEnd={activeNode === 5 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={productsVisible ? 1 : 0}
          className="transition-opacity duration-300"
        />

        {/* Edge 5C: DFT Refinement (165, 248) -> Product C (420, 305) */}
        {/* ONLY APPEARS WHEN MOLECULE LEAVES DFT REFINEMENT */}
        <path
          ref={path5CRef}
          d="M 165 248 C 275 248, 315 305, 420 305"
          fill="none"
          stroke={activeNode === 4 ? '#f97316' : '#cbd5e1'}
          strokeWidth="1.5"
          markerEnd={activeNode === 4 ? 'url(#arr-orange)' : 'url(#arr-slate)'}
          opacity={productsVisible ? 0.8 : 0}
          className="transition-opacity duration-300"
        />

        {/* ======================================================== */}
        {/* PURE NODES (Clean, compact, no emojis, no icons) */}
        {/* ======================================================== */}

        {/* 1. Reactant */}
        <g
          transform="translate(15, 25)"
          opacity={buildStep >= 0 ? 1 : 0.15}
          filter="url(#node-shadow)"
          className="transition-all duration-300"
        >
          <rect
            width="95"
            height="36"
            rx="7"
            fill={activeNode === 0 ? '#fff7ed' : '#ffffff'}
            stroke={activeNode === 0 ? '#f97316' : '#cbd5e1'}
            strokeWidth={activeNode === 0 ? '2' : '1.5'}
          />
          <text
            x="47.5"
            y="23"
            textAnchor="middle"
            fill={activeNode === 0 ? '#c2410c' : '#1e293b'}
            fontSize="12.5"
            fontWeight="600"
          >
            Reactant
          </text>
        </g>

        {/* 2. MLFF Geometry Opt */}
        <g
          transform="translate(180, 25)"
          opacity={buildStep >= 1 ? 1 : 0.15}
          filter="url(#node-shadow)"
          className="transition-all duration-300"
        >
          <rect
            width="135"
            height="36"
            rx="7"
            fill={activeNode === 1 ? '#fff7ed' : '#ffffff'}
            stroke={activeNode === 1 ? '#f97316' : '#cbd5e1'}
            strokeWidth={activeNode === 1 ? '2' : '1.5'}
          />
          <text
            x="67.5"
            y="23"
            textAnchor="middle"
            fill={activeNode === 1 ? '#c2410c' : '#1e293b'}
            fontSize="12.5"
            fontWeight="600"
          >
            MLFF Geom Opt
          </text>
        </g>

        {/* 3. Reactive MD */}
        <g
          transform="translate(380, 25)"
          opacity={buildStep >= 2 ? 1 : 0.15}
          filter="url(#node-shadow)"
          className="transition-all duration-300"
        >
          <rect
            width="115"
            height="36"
            rx="7"
            fill={activeNode === 2 ? '#fff7ed' : '#ffffff'}
            stroke={activeNode === 2 ? '#f97316' : '#cbd5e1'}
            strokeWidth={activeNode === 2 ? '2' : '1.5'}
          />
          <text
            x="57.5"
            y="23"
            textAnchor="middle"
            fill={activeNode === 2 ? '#c2410c' : '#1e293b'}
            fontSize="12.5"
            fontWeight="600"
          >
            Reactive MD
          </text>
        </g>

        {/* 4. Conformer Sampling */}
        <g
          transform="translate(250, 130)"
          opacity={buildStep >= 3 ? 1 : 0.15}
          filter="url(#node-shadow)"
          className="transition-all duration-300"
        >
          <rect
            width="145"
            height="36"
            rx="7"
            fill={activeNode === 3 ? '#fff7ed' : '#ffffff'}
            stroke={activeNode === 3 ? '#f97316' : '#cbd5e1'}
            strokeWidth={activeNode === 3 ? '2' : '1.5'}
          />
          <text
            x="72.5"
            y="23"
            textAnchor="middle"
            fill={activeNode === 3 ? '#c2410c' : '#1e293b'}
            fontSize="12.5"
            fontWeight="600"
          >
            Conformer Sampling
          </text>
        </g>

        {/* 5. DFT Refinement */}
        <g
          transform="translate(35, 230)"
          opacity={buildStep >= 4 ? 1 : 0.15}
          filter="url(#node-shadow)"
          className="transition-all duration-300"
        >
          <rect
            width="130"
            height="36"
            rx="7"
            fill={activeNode === 4 ? '#fff7ed' : '#ffffff'}
            stroke={activeNode === 4 ? '#f97316' : '#cbd5e1'}
            strokeWidth={activeNode === 4 ? '2' : '1.5'}
          />
          <text
            x="65"
            y="23"
            textAnchor="middle"
            fill={activeNode === 4 ? '#c2410c' : '#1e293b'}
            fontSize="12.5"
            fontWeight="600"
          >
            DFT Refinement
          </text>
        </g>

        {/* ======================================================== */}
        {/* THREE PRODUCTS (Appear ONLY when molecule leaves DFT refinement) */}
        {/* ======================================================== */}

        {/* Product A */}
        <g
          transform="translate(420, 180)"
          opacity={productsVisible ? 1 : 0}
          filter="url(#node-shadow)"
          className="transition-opacity duration-300"
        >
          <rect
            width="95"
            height="30"
            rx="6"
            fill="#ffffff"
            stroke="#cbd5e1"
            strokeWidth="1.5"
          />
          <text
            x="47.5"
            y="19"
            textAnchor="middle"
            fill="#64748b"
            fontSize="11.5"
            fontWeight="500"
          >
            Product A
          </text>
        </g>

        {/* Product B: Marked as Highest Probable */}
        <g
          transform="translate(390, 230)"
          opacity={productsVisible ? 1 : 0}
          filter="url(#node-shadow)"
          className="transition-opacity duration-300"
        >
          <rect
            width="165"
            height="38"
            rx="7"
            fill={activeNode === 5 ? '#fff7ed' : '#ffffff'}
            stroke="#f97316"
            strokeWidth={activeNode === 5 ? '2.5' : '2'}
          />
          <text
            x="82.5"
            y="18"
            textAnchor="middle"
            fill="#ea580c"
            fontSize="10"
            fontWeight="700"
            letterSpacing="0.04em"
          >
            HIGHEST PROBABLE
          </text>
          <text
            x="82.5"
            y="31"
            textAnchor="middle"
            fill="#0f172a"
            fontSize="11"
            fontWeight="600"
          >
            Product B
          </text>
        </g>

        {/* Product C */}
        <g
          transform="translate(420, 290)"
          opacity={productsVisible ? 1 : 0}
          filter="url(#node-shadow)"
          className="transition-opacity duration-300"
        >
          <rect
            width="95"
            height="30"
            rx="6"
            fill="#ffffff"
            stroke="#cbd5e1"
            strokeWidth="1.5"
          />
          <text
            x="47.5"
            y="19"
            textAnchor="middle"
            fill="#64748b"
            fontSize="11.5"
            fontWeight="500"
          >
            Product C
          </text>
        </g>

        {/* ======================================================== */}
        {/* TRAVELING SYMBOLIC MOLECULE TOKEN */}
        {/* ======================================================== */}
        {phase === 'simulating' && simProgress < 0.98 && (
          <g
            transform={`translate(${molPos.x}, ${molPos.y}) rotate(${molPos.angle})`}
            className="pointer-events-none"
          >
            {/* Soft glow halo */}
            <circle cx="0" cy="0" r="12" fill="#f97316" fillOpacity="0.25" />
            {/* Center atom */}
            <circle cx="0" cy="0" r="5" fill="#ea580c" />
            {/* Bonded atoms */}
            <circle cx="-5.5" cy="-5.5" r="3" fill="#0284c7" />
            <circle cx="5.5" cy="-5.5" r="3" fill="#0284c7" />
            <circle cx="0" cy="7" r="3" fill="#475569" />
            {/* Bonds */}
            <line x1="0" y1="0" x2="-5.5" y2="-5.5" stroke="#ea580c" strokeWidth="1.2" />
            <line x1="0" y1="0" x2="5.5" y2="-5.5" stroke="#ea580c" strokeWidth="1.2" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="#ea580c" strokeWidth="1.2" />
          </g>
        )}

        {/* Split particles heading to products A and C when molecule leaves DFT */}
        {phase === 'simulating' && productsVisible && simProgress < 0.98 && (
          <>
            <circle cx={productParticles.a.x} cy={productParticles.a.y} r="3" fill="#94a3b8" />
            <circle cx={productParticles.c.x} cy={productParticles.c.y} r="3" fill="#94a3b8" />
          </>
        )}
      </svg>
    </div>
  );
}
