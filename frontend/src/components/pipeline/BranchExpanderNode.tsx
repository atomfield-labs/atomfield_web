import { MoreVertical, ChevronUp, Plus } from 'lucide-react';

export interface BranchExpanderData {
  groupId: string;
  hiddenCount: number;
  totalIntermediate: number;
  batchSize?: number;
  isFullyExpanded: boolean;
  onExpandBatch?: (groupId: string) => void;
  onCollapseGroup?: (groupId: string) => void;
}

export default function BranchExpanderNode({ data }: { data: BranchExpanderData }) {
  const hiddenCount = data.hiddenCount ?? 0;
  const isFullyExpanded = data.isFullyExpanded || hiddenCount === 0;
  const batchSize = data.batchSize || 5;
  const nextExpandCount = Math.min(batchSize, hiddenCount);

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        if (!isFullyExpanded && data.onExpandBatch) {
          data.onExpandBatch(data.groupId);
        } else if (isFullyExpanded && data.onCollapseGroup) {
          data.onCollapseGroup(data.groupId);
        }
      }}
      className="nodrag w-[200px] bg-white border-2 border-dashed border-slate-300 hover:border-orange-400 hover:bg-orange-50/80 rounded-xl px-3 py-2 flex items-center justify-between shadow-2xs transition-all cursor-pointer select-none group"
      title={
        isFullyExpanded
          ? 'All parallel jobs expanded. Click to collapse.'
          : `Click to expand next ${nextExpandCount} parallel job(s).`
      }
    >
      {/* Left: Three Vertical Dots + Counter */}
      <div className="flex items-center gap-1.5 min-w-0">
        <div className="flex flex-col items-center justify-center text-slate-400 group-hover:text-orange-500 transition-colors">
          <MoreVertical className="w-4 h-4 stroke-[2.5]" />
        </div>
        <div className="flex flex-col min-w-0">
          <span className="text-[11px] font-bold text-slate-700 group-hover:text-slate-900 truncate">
            {isFullyExpanded ? 'All jobs visible' : `${hiddenCount} jobs hidden`}
          </span>
          <span className="text-[9px] font-mono text-slate-400">
            {isFullyExpanded ? 'Batch complete' : `Batch size: ${batchSize}`}
          </span>
        </div>
      </div>

      {/* Right: Expand / Collapse Pill */}
      <div>
        {!isFullyExpanded ? (
          <span className="px-2 py-0.5 text-[10px] font-bold text-orange-600 bg-orange-50 group-hover:bg-orange-100 border border-orange-200 rounded-md transition-colors flex items-center gap-0.5 shadow-2xs">
            <Plus className="w-3 h-3 stroke-[3]" />
            <span>{nextExpandCount}</span>
          </span>
        ) : (
          <span className="px-2 py-0.5 text-[10px] font-bold text-slate-600 bg-slate-100 group-hover:bg-slate-200 border border-slate-200 rounded-md transition-colors flex items-center gap-0.5 shadow-2xs">
            <ChevronUp className="w-3 h-3 stroke-[2.5]" />
            <span>Fold</span>
          </span>
        )}
      </div>
    </div>
  );
}
