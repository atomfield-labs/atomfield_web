import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { pipelineService, authService } from '../../api/services';
import PipelineHUD from './PipelineHUD';
import GraphCanvas from './GraphCanvas';
import InspectorDrawer from './InspectorDrawer';

export interface PipelineNodeData {
  label: string;
  status: 'Pending' | 'Running' | 'Success' | 'Failed' | 'Blocked';
  parameters: any;
  logs?: string;
}

export default function PipelineView() {
  const [blueprint, setBlueprint] = useState<{ nodes: any[]; edges: any[] } | null>(null);
  const [quota, setQuota] = useState<number | null>(null);
  const [selectedNode, setSelectedNode] = useState<any | null>(null);

  useEffect(() => {
    // Fetch topology and quota
    const fetchData = async () => {
      try {
        const bpData = await pipelineService.getNanoreactorBlueprint();
        setBlueprint(bpData);
        
        const quotaData = await authService.getQuota();
        setQuota(quotaData.runsRemaining);
      } catch (err) {
        console.error("Failed to fetch pipeline data:", err);
      }
    };
    fetchData();
  }, []);

  const handleLaunch = () => {
    alert("Launching pipeline...");
    // Implementation for actually executing the pipeline
  };

  return (
    <div className="flex flex-col h-screen w-full bg-slate-50">
      <PipelineHUD quota={quota} onLaunch={handleLaunch} />
      
      <div className="flex flex-1 overflow-hidden relative">
        <div className="flex-1 h-full">
          {blueprint ? (
            <ReactFlowProvider>
              <GraphCanvas 
                blueprint={blueprint} 
                onNodeClick={(node) => setSelectedNode(node)} 
              />
            </ReactFlowProvider>
          ) : (
            <div className="w-full h-full flex items-center justify-center font-bold text-slate-400">
              Loading DAG Topology...
            </div>
          )}
        </div>
        
        <InspectorDrawer 
          node={selectedNode} 
          onClose={() => setSelectedNode(null)} 
        />
      </div>
    </div>
  );
}
