import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

export interface CalculationNodeData {
  label?: string;
  filename?: string;
  script_id?: string;
  status?: string;
  parameters?: Record<string, any>;
  default_parameters?: Record<string, any>;
  originalData?: any;
}

// Clean, static edge joints positioned directly on the box lines
const handleBaseClass =
  "!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair";

function CalculationNode({
  data,
  isConnectable = true,
}: {
  data: CalculationNodeData;
  isConnectable?: boolean;
}) {
  const label = data.label || data.filename || 'Calculation Step';
  const status = (data.status || 'Draft').toLowerCase();
  const isSuccess = status === 'success' || status === 'completed';
  const isRunning = status === 'running';
  const isFailed = status === 'failed';

  return (
    <div
      className={`relative w-full h-full select-none rounded-[10px] transition-all duration-200 ${
        isSuccess
          ? 'bg-emerald-50 text-emerald-950 ring-2 ring-emerald-500 shadow-sm'
          : isRunning
          ? 'bg-blue-50 text-blue-950 ring-2 ring-blue-500 animate-pulse shadow-sm'
          : isFailed
          ? 'bg-rose-50 text-rose-950 ring-2 ring-rose-500 shadow-sm'
          : 'bg-white text-slate-800'
      }`}
    >
      {/* PRIMARY OUTGOING: Right side is the default exit joint */}
      <Handle
        type="source"
        position={Position.Right}
        id="source-right"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />

      {/* PRIMARY INCOMING: Left side is the default entry joint */}
      <Handle
        type="target"
        position={Position.Left}
        id="target-left"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />

      {/* TOP JOINT: Incoming from above by default */}
      <Handle
        type="target"
        position={Position.Top}
        id="target-top"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />
      <Handle
        type="source"
        position={Position.Top}
        id="source-top"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />

      {/* BOTTOM JOINT: Outgoing to below by default */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="source-bottom"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="target-bottom"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />

      {/* REVERSE / SECONDARY JOINTS */}
      <Handle
        type="source"
        position={Position.Left}
        id="source-left"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />
      <Handle
        type="target"
        position={Position.Right}
        id="target-right"
        isConnectable={isConnectable}
        className={handleBaseClass}
      />

      {/* Padded Node Content with Status Indicator */}
      <div className="w-full h-full px-3.5 py-2.5 flex items-center justify-center gap-2">
        {isSuccess && (
          <span
            className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-300 shrink-0 inline-block"
            title="Completed"
          />
        )}
        {isRunning && (
          <span
            className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse shrink-0 inline-block"
            title="Running"
          />
        )}
        {isFailed && (
          <span
            className="w-2.5 h-2.5 rounded-full bg-rose-500 shrink-0 inline-block"
            title="Failed"
          />
        )}
        <span className="truncate leading-tight font-bold text-center pointer-events-none">
          {label}
        </span>
      </div>
    </div>
  );
}

export default memo(CalculationNode);
