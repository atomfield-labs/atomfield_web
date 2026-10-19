import { Handle, Position } from '@xyflow/react';

interface ResultViewerNodeProps {
  data: {
    label?: string;
    subtitle?: string;
    status?: string;
    speciesCount?: number;
    pathwayCount?: number;
    onOpenResults?: () => void;
  };
  selected?: boolean;
}

export default function ResultViewerNode({
  data,
  selected = false,
}: ResultViewerNodeProps) {
  const label = data.label || 'Reaction Network Explorer';
  const speciesCount = data.speciesCount || 7;
  const pathwayCount = data.pathwayCount || 6;

  return (
    <div
      className={`relative min-w-[220px] max-w-[260px] bg-white rounded-lg border transition-all duration-150 select-none shadow-xs ${
        selected
          ? 'border-orange-500 ring-2 ring-orange-100 shadow-sm'
          : 'border-slate-300 hover:border-slate-400'
      }`}
    >
      {/* Static Connection Ports on Box Lines */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        className="!w-2 !h-2 !bg-slate-300 !border !border-slate-500 !rounded-full !-left-1"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        className="!w-2 !h-2 !bg-slate-300 !border !border-slate-500 !rounded-full !-right-1"
      />
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        className="!w-2 !h-2 !bg-slate-300 !border !border-slate-500 !rounded-full !-top-1"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        className="!w-2 !h-2 !bg-slate-300 !border !border-slate-500 !rounded-full !-bottom-1"
      />

      {/* Header with Status Pill */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100 bg-slate-50/60 rounded-t-lg">
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider font-semibold">
          Results Output
        </span>
        <span className="px-1.5 py-0.5 text-[9.5px] font-mono font-bold text-emerald-700 bg-emerald-50 border border-emerald-200/80 rounded">
          READY
        </span>
      </div>

      {/* Node Content */}
      <div className="p-3 flex flex-col gap-2">
        <div>
          <h4 className="text-xs font-bold text-slate-900 leading-snug">
            {label}
          </h4>
          <p className="text-[10.5px] text-slate-500 font-mono mt-0.5">
            {speciesCount} species • {pathwayCount} pathways
          </p>
        </div>

        {/* Action Button */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (data.onOpenResults) {
              data.onOpenResults();
            }
          }}
          className="w-full mt-1 py-1.5 px-3 bg-orange-600 hover:bg-orange-700 text-white rounded text-xs font-medium transition-colors text-center cursor-pointer shadow-xs"
        >
          View 3D Network & Files
        </button>
      </div>
    </div>
  );
}
