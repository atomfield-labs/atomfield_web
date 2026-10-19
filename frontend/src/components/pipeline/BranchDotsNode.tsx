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
      className="nodrag w-9 h-9 rounded-full bg-white border-2 border-dashed border-slate-300 hover:border-orange-500 hover:bg-orange-50 flex flex-col items-center justify-center shadow-2xs hover:scale-105 transition-all cursor-pointer select-none group"
      title={
        isFullyExpanded
          ? `All jobs on ${data.side} side expanded. Click to collapse.`
          : `${hiddenCount} jobs hidden on ${data.side} side. Click to expand next ${nextExpandCount}.`
      }
    >
      <div className="flex flex-col items-center justify-center -space-y-0.5">
        {!isFullyExpanded ? (
          <>
            <MoreVertical className="w-3.5 h-3.5 text-slate-400 group-hover:text-orange-500 transition-colors" />
            <span className="text-[8px] font-mono font-bold text-orange-600 leading-none">
              +{nextExpandCount}
            </span>
          </>
        ) : (
          <>
            {data.side === 'up' ? (
              <ChevronDown className="w-3.5 h-3.5 text-slate-500 group-hover:text-orange-500 transition-colors" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5 text-slate-500 group-hover:text-orange-500 transition-colors" />
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
