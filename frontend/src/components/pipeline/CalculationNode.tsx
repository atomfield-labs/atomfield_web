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

  return (
    <div className="relative w-full h-full select-none">
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

      {/* Padded Node Content */}
      <div className="w-full h-full px-3.5 py-2.5 flex items-center justify-center">
        <span className="truncate leading-tight font-bold text-center pointer-events-none">
          {label}
        </span>
      </div>
    </div>
  );
}

export default memo(CalculationNode);
