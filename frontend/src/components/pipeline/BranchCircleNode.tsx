import { Handle } from '@xyflow/react';
import StatusIcon from '../StatusIcon';
import { STATUS_TEXT, statusLook } from '../../utils/jobStatus';
import { HANDLE_CLASS, STEP_HANDLES } from './nodeStyle';

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

const CIRCLE = [
  'nodrag relative w-9 h-9 rounded-full bg-white border border-stone-200',
  'shadow-[0_1px_2px_rgba(28,25,23,0.05)] hover:border-stone-300',
  'flex items-center justify-center text-xs font-medium text-stone-600',
  'cursor-pointer select-none',
].join(' ');

/**
 * One copy of a step in a sweep: its number until it runs, then its
 * status icon.
 */
export default function BranchCircleNode({ data }: { data: BranchCircleData }) {
  const look = statusLook(data.status);
  const index = data.index || 1;
  const label = data.label || 'Step';
  return (
    <div className={CIRCLE} title={`${label} #${index}: ${STATUS_TEXT[look]}`}>
      {STEP_HANDLES.map((handle) => (
        <Handle
          key={handle.id}
          id={handle.id}
          type={handle.type}
          position={handle.position}
          className={HANDLE_CLASS}
        />
      ))}
      {look === 'none' ? (
        <span>{index}</span>
      ) : (
        <StatusIcon status={data.status} size={14} />
      )}
    </div>
  );
}
