import { memo } from 'react';
import { Handle } from '@xyflow/react';
import StatusIcon from '../StatusIcon';
import { statusLook } from '../../utils/jobStatus';
import { HANDLE_CLASS, STEP_HANDLES, nodeBox } from './nodeStyle';

export interface CalculationNodeData {
  label?: string;
  filename?: string;
  script_id?: string;
  status?: string;
  parameters?: Record<string, any>;
  default_parameters?: Record<string, any>;
  originalData?: any;
}

/**
 * One step: its name and a small status icon, nothing louder.
 */
function CalculationNode({
  data,
  selected = false,
  isConnectable = true,
}: {
  data: CalculationNodeData;
  selected?: boolean;
  isConnectable?: boolean;
}) {
  const label = data.label || data.filename || 'Step';
  const waiting = statusLook(data.status) === 'waiting';
  const text = waiting ? 'text-stone-600' : 'text-stone-900';
  return (
    <div className={nodeBox(selected, waiting)} title={label}>
      {STEP_HANDLES.map((handle) => (
        <Handle
          key={handle.id}
          id={handle.id}
          type={handle.type}
          position={handle.position}
          isConnectable={isConnectable}
          className={HANDLE_CLASS}
        />
      ))}
      <StatusIcon status={data.status} />
      <span className={`truncate text-sm font-medium ${text}`}>{label}</span>
    </div>
  );
}

export default memo(CalculationNode);
