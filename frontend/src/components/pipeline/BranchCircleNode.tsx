import { Handle, Position } from '@xyflow/react';

export interface BranchCircleData {
  index: number;
  label: string;
  status?: string;
  script_id?: string;
  ui_id?: string;
  parameters?: Record<string, any>;
  default_parameters?: Record<string, any>;
  originalData?: any;
  branchGroupId?: string;
}

const statusStyles: Record<string, { bg: string; border: string; text: string }> = {
  Draft: { bg: 'bg-white hover:bg-orange-50/90', border: 'border-slate-300 hover:border-orange-500', text: 'text-slate-700' },
  Ready: { bg: 'bg-white hover:bg-orange-50/90', border: 'border-slate-300 hover:border-orange-500', text: 'text-slate-700' },
  Pending: { bg: 'bg-amber-50 hover:bg-orange-50/90', border: 'border-amber-400 hover:border-orange-500', text: 'text-amber-800' },
  Running: { bg: 'bg-blue-500 hover:bg-blue-600', border: 'border-blue-600 ring-2 ring-blue-300 animate-pulse', text: 'text-white' },
  Success: { bg: 'bg-emerald-500 hover:bg-emerald-600', border: 'border-emerald-600 ring-2 ring-emerald-300', text: 'text-white' },
  Completed: { bg: 'bg-emerald-500 hover:bg-emerald-600', border: 'border-emerald-600 ring-2 ring-emerald-300', text: 'text-white' },
  Failed: { bg: 'bg-rose-500 hover:bg-rose-600', border: 'border-rose-600 ring-2 ring-rose-300', text: 'text-white' },
  Blocked: { bg: 'bg-slate-100 hover:bg-orange-50/90', border: 'border-slate-400 hover:border-orange-500', text: 'text-slate-500' },
};

export default function BranchCircleNode({ data }: { data: BranchCircleData }) {
  const rawStatus = data.status || 'Draft';
  const lower = rawStatus.toLowerCase();
  const normalized = (lower === 'success' || lower === 'completed') ? 'Success' : rawStatus;
  const style = statusStyles[normalized] || statusStyles['Draft'];
  const displayIndex = data.index || 1;

  return (
    <div
      className={`nodrag relative w-9 h-9 rounded-full ${style.bg} border-2 ${style.border} ${style.text} flex items-center justify-center font-mono font-bold text-xs shadow-2xs hover:shadow-md hover:scale-110 transition-all cursor-pointer select-none group`}
      title={`${data.label || 'Calculation'} #${displayIndex} (${status}) - Double-click to inspect parameters`}
    >
      {/* 1. Right Joint (Primary Outgoing Source) */}
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />

      {/* 2. Left Joint (Primary Incoming Target) */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />

      {/* 3. Top Joint */}
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />
      <Handle
        type="source"
        position={Position.Top}
        id="source-top"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />

      <span>{displayIndex}</span>

      {/* 4. Bottom Joint */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="target-bottom"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />

      {/* Secondary Reverse Handles */}
      <Handle
        type="source"
        position={Position.Left}
        id="source-left"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />
      <Handle
        type="target"
        position={Position.Right}
        id="target-right"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10"
      />
    </div>
  );
}
