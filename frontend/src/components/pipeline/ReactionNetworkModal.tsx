import { useState, useEffect, useRef } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { jobsService } from '../../api/services';

interface ReactionNetworkModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string;
  jobId?: string;
}

interface GraphNode {
  id: string;
  name?: string;
  smiles?: string;
  formula?: string;
  node_type?: string;
  energy_ev?: number;
  conformers?: number;
  fx?: number;
  fy?: number;
  fz?: number;
  [key: string]: any;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  reaction?: string;
  Ea?: number;
  delta_E?: number;
  [key: string]: any;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface TextFileItem {
  filename: string;
  content: string;
  size_bytes: number;
}

const FALLBACK_GRAPH_DATA: GraphData = {
  nodes: [
    {
      id: 'CCO',
      name: 'Ethanol',
      smiles: 'CCO',
      formula: 'C2H6O',
      node_type: 'Reactant',
      energy_ev: -154.215,
      conformers: 12,
      fx: 0,
      fy: 0,
      fz: 0,
    },
    {
      id: 'C=C',
      name: 'Ethylene',
      smiles: 'C=C',
      formula: 'C2H4',
      node_type: 'Product',
      energy_ev: -78.102,
      conformers: 8,
    },
    {
      id: 'O',
      name: 'Water',
      smiles: 'O',
      formula: 'H2O',
      node_type: 'Product',
      energy_ev: -76.054,
      conformers: 14,
    },
    {
      id: 'CC=O',
      name: 'Acetaldehyde',
      smiles: 'CC=O',
      formula: 'C2H4O',
      node_type: 'Intermediate',
      energy_ev: -152.882,
      conformers: 6,
    },
    {
      id: '[H][H]',
      name: 'Hydrogen Gas',
      smiles: '[H][H]',
      formula: 'H2',
      node_type: 'Product',
      energy_ev: -6.741,
      conformers: 9,
    },
    {
      id: '[C-]#[O+]',
      name: 'Carbon Monoxide',
      smiles: '[C-]#[O+]',
      formula: 'CO',
      node_type: 'Product',
      energy_ev: -113.805,
      conformers: 4,
    },
    {
      id: 'C',
      name: 'Methane',
      smiles: 'C',
      formula: 'CH4',
      node_type: 'Product',
      energy_ev: -40.501,
      conformers: 5,
    },
  ],
  links: [
    {
      source: 'CCO',
      target: 'C=C',
      reaction: 'Dehydration: C2H6O -> C2H4 + H2O',
      Ea: 1.85,
      delta_E: 0.059,
    },
    {
      source: 'CCO',
      target: 'O',
      reaction: 'Dehydration Coproduct',
      Ea: 1.85,
      delta_E: 0.059,
    },
    {
      source: 'CCO',
      target: 'CC=O',
      reaction: 'Dehydrogenation: C2H6O -> C2H4O + H2',
      Ea: 2.15,
      delta_E: 1.333,
    },
    {
      source: 'CCO',
      target: '[H][H]',
      reaction: 'Dehydrogenation Coproduct',
      Ea: 2.15,
      delta_E: 1.333,
    },
    {
      source: 'CC=O',
      target: 'C',
      reaction: 'Decarbonylation: C2H4O -> CH4 + CO',
      Ea: 2.9,
      delta_E: -1.424,
    },
    {
      source: 'CC=O',
      target: '[C-]#[O+]',
      reaction: 'Decarbonylation Coproduct',
      Ea: 2.9,
      delta_E: -1.424,
    },
  ],
};

export default function ReactionNetworkModal({
  isOpen,
  onClose,
  sessionId,
  jobId,
}: ReactionNetworkModalProps) {
  const [activeTab, setActiveTab] = useState<'network' | 'files'>('network');
  const [textFiles, setTextFiles] = useState<TextFileItem[]>([]);
  const [selectedFileIdx, setSelectedFileIdx] = useState(0);
  const [graphData, setGraphData] = useState<GraphData>(FALLBACK_GRAPH_DATA);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const graphContainerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Load artifacts from backend
  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);

    jobsService
      .getTextArtifacts({ jobId, sessionId })
      .then((data) => {
        if (data && data.files && data.files.length > 0) {
          setTextFiles(data.files);

          // Find network.json
          const networkFile = data.files.find(
            (f) =>
              f.filename.includes('network') ||
              f.filename.endsWith('.json')
          );
          if (networkFile) {
            try {
              const parsed = JSON.parse(networkFile.content);
              if (parsed.nodes && parsed.links) {
                // Pin reactant at center if found
                const nodes = parsed.nodes.map((n: GraphNode) => {
                  if (n.node_type === 'Reactant' || n.id === 'CCO') {
                    return { ...n, fx: 0, fy: 0, fz: 0 };
                  }
                  return n;
                });
                setGraphData({ nodes, links: parsed.links });
              }
            } catch (err) {
              console.warn('Using fallback network data:', err);
              setGraphData(FALLBACK_GRAPH_DATA);
            }
          }
        }
      })
      .catch((err) => {
        console.warn('Failed to fetch text artifacts, using default:', err);
        setGraphData(FALLBACK_GRAPH_DATA);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [isOpen, jobId, sessionId]);

  // Track container size for 3D canvas
  useEffect(() => {
    if (!isOpen || activeTab !== 'network') return;
    const updateSize = () => {
      if (graphContainerRef.current) {
        setDimensions({
          width: graphContainerRef.current.clientWidth,
          height: graphContainerRef.current.clientHeight,
        });
      }
    };
    updateSize();
    const timer = setTimeout(updateSize, 100);
    window.addEventListener('resize', updateSize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateSize);
    };
  }, [isOpen, activeTab]);

  const activeFile = textFiles[selectedFileIdx] || textFiles[0];

  const handleCopy = () => {
    if (activeFile?.content) {
      navigator.clipboard.writeText(activeFile.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 select-none animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="relative w-[94vw] h-[90vh] max-w-6xl bg-white rounded-xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Nanoreactor Discovery Results
            </h3>
            {isLoading ? (
              <span className="text-[11px] font-mono text-orange-600 animate-pulse font-medium">
                Loading artifacts...
              </span>
            ) : sessionId ? (
              <span className="text-[11px] font-mono text-slate-500 bg-slate-200/60 px-2 py-0.5 rounded">
                Session: {sessionId.substring(0, 10)}
              </span>
            ) : null}
          </div>

          {/* Clean Tab Switcher */}
          <div className="flex items-center bg-slate-200/80 p-0.5 rounded-lg border border-slate-300/60">
            <button
              type="button"
              onClick={() => setActiveTab('network')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors cursor-pointer ${
                activeTab === 'network'
                  ? 'bg-white text-orange-600 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              3D Reaction Network
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('files')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors cursor-pointer ${
                activeTab === 'files'
                  ? 'bg-white text-orange-600 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Text Artifacts ({textFiles.length || 3})
            </button>
          </div>

          {/* Close Button */}
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-slate-200 text-slate-500 hover:text-slate-800 text-lg font-bold transition-colors cursor-pointer leading-none"
            title="Close"
          >
            &times;
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 min-h-0 relative">
          {/* TAB 1: 3D REACTION NETWORK */}
          {activeTab === 'network' && (
            <div ref={graphContainerRef} className="w-full h-full relative bg-slate-950">
              <ForceGraph3D
                width={dimensions.width}
                height={dimensions.height}
                graphData={graphData}
                backgroundColor="#090d16"
                nodeLabel={(node: any) => `${node.name || node.id} (${node.formula || ''})`}
                nodeColor={(node: any) => {
                  if (node.node_type === 'Reactant' || node.id === 'CCO') return '#ea580c'; // Orange for Reactant
                  if (node.node_type === 'Intermediate') return '#10b981'; // Emerald
                  return '#0284c7'; // Blue for Products
                }}
                nodeVal={(node: any) => (node.node_type === 'Reactant' ? 8 : 4)}
                nodeRelSize={4}
                nodeResolution={16}
                linkColor={() => '#475569'}
                linkWidth={1.5}
                linkDirectionalArrowLength={3.5}
                linkDirectionalArrowRelPos={1}
                linkLabel={(link: any) => link.reaction || (link.Ea ? `Ea: ${link.Ea} eV` : '')}
                onNodeClick={(node: any) => setSelectedNode(node)}
              />

              {/* Legend & Selected Node Overlay */}
              <div className="absolute top-4 left-4 bg-slate-900/85 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-300 pointer-events-none shadow-lg">
                <div className="text-[11px] font-bold text-slate-200 mb-1">Legend</div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-orange-600" />
                  <span>Reactant (Ethanol)</span>
                </div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-sky-600" />
                  <span>Discovered Products</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <span>Intermediates</span>
                </div>
              </div>

              {/* Clicked Species Inspection Panel */}
              {selectedNode && (
                <div className="absolute bottom-4 right-4 max-w-xs w-80 bg-slate-900/90 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 shadow-xl backdrop-blur-xs select-text">
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <span className="font-bold text-orange-400 text-sm">
                      {selectedNode.name || selectedNode.id}
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedNode(null)}
                      className="text-slate-400 hover:text-white font-bold cursor-pointer"
                    >
                      &times;
                    </button>
                  </div>
                  <div className="mt-2 space-y-1 font-mono text-[11px]">
                    <div><span className="text-slate-400">Formula:</span> {selectedNode.formula || '—'}</div>
                    <div><span className="text-slate-400">SMILES:</span> {selectedNode.smiles || selectedNode.id}</div>
                    <div><span className="text-slate-400">Role:</span> {selectedNode.node_type || 'Product'}</div>
                    {selectedNode.energy_ev !== undefined && (
                      <div><span className="text-slate-400">Rel Energy:</span> {selectedNode.energy_ev} eV</div>
                    )}
                    {selectedNode.conformers && (
                      <div><span className="text-slate-400">Conformers:</span> {selectedNode.conformers}</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: TEXT ARTIFACTS ONLY */}
          {activeTab === 'files' && (
            <div className="w-full h-full flex bg-slate-900">
              {/* File list sidebar */}
              <div className="w-56 border-r border-slate-800 bg-slate-950 p-2 flex flex-col gap-1 overflow-y-auto shrink-0">
                <div className="px-2 py-1.5 text-[10.5px] font-mono font-bold text-slate-400 uppercase tracking-wider">
                  Text Outputs
                </div>
                {textFiles.map((file, idx) => (
                  <button
                    key={file.filename}
                    type="button"
                    onClick={() => setSelectedFileIdx(idx)}
                    className={`w-full text-left px-2.5 py-1.5 rounded text-xs font-mono truncate transition-colors cursor-pointer ${
                      selectedFileIdx === idx
                        ? 'bg-slate-800 text-orange-400 font-bold'
                        : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                    }`}
                  >
                    {file.filename}
                  </button>
                ))}
              </div>

              {/* File Content Pane */}
              <div className="flex-1 flex flex-col min-w-0 bg-slate-900">
                {activeFile ? (
                  <>
                    <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800 bg-slate-950/60">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-slate-200">
                          {activeFile.filename}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">
                          ({(activeFile.size_bytes / 1024).toFixed(1)} KB)
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={handleCopy}
                        className="px-2.5 py-1 text-xs font-mono font-medium rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
                      >
                        {copied ? 'Copied' : 'Copy Content'}
                      </button>
                    </div>
                    <pre className="flex-1 p-4 overflow-auto font-mono text-xs text-slate-300 leading-relaxed whitespace-pre-wrap select-text">
                      {activeFile.content}
                    </pre>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-slate-500 font-mono text-xs">
                    No text file selected.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
