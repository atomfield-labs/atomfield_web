import { MoreVertical, ChevronUp, ChevronDown } from 'lucide-react';

export interface BranchDotsData {
  groupId: string;
  side: 'up' | 'down';
  hiddenCount: number;
  totalIntermediate: number;
  batchSize?: number;
  isFullyExpanded: boolean;
  intermediateNodeIds?: string[];
  boundaryNodeId?: string;
  closestNodeId?: string;
  onExpandSide?: (groupId: string, side: 'up' | 'down') => void;
  onCollapseSide?: (groupId: string, side: 'up' | 'down') => void;
}

// The dots at a sweep's end: show or fold its hidden copies.
const DOTS = [
  'nodrag w-9 h-9 rounded-full bg-white border border-dashed',
  'border-stone-300 hover:border-stone-400 hover:bg-stone-50',
  'flex flex-col items-center justify-center transition-all',
  'cursor-pointer select-none group',
].join(' ');
const ICON = 'w-3.5 h-3.5 group-hover:text-stone-600 transition-colors';
const COUNT = 'text-[8px] font-mono font-bold text-stone-600 leading-none';

export default function BranchDotsNode({ data }: { data: BranchDotsData }) {
  const hiddenCount = data.hiddenCount ?? 0;
  const isFullyExpanded = data.isFullyExpanded || hiddenCount === 0;
  const batchSize = data.batchSize || 5;
  const nextExpandCount = Math.min(batchSize, hiddenCount);

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        if (!isFullyExpanded && data.onExpandSide) {
          data.onExpandSide(data.groupId, data.side);
        } else if (isFullyExpanded && data.onCollapseSide) {
          data.onCollapseSide(data.groupId, data.side);
        }
      }}
      className={DOTS}
      title={
        isFullyExpanded
          ? `All jobs on ${data.side} side expanded. Click to collapse.`
          : `${hiddenCount} jobs hidden on ${data.side} side. Click to expand next ${nextExpandCount}.`
      }
    >
      <div className="flex flex-col items-center justify-center -space-y-0.5">
        {!isFullyExpanded ? (
          <>
            <MoreVertical className={`${ICON} text-stone-400`} />
            <span className={COUNT}>
              +{nextExpandCount}
            </span>
          </>
        ) : (
          <>
            {data.side === 'up' ? (
              <ChevronDown className={`${ICON} text-stone-500`} />
            ) : (
              <ChevronUp className={`${ICON} text-stone-500`} />
            )}
            <span className="text-[8px] font-mono font-bold text-slate-500 leading-none">
              Fold
            </span>
          </>
        )}
      </div>
    </div>
  );
}
