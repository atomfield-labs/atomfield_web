
interface PipelineHUDProps {
  quota?: number | null;
  onLaunch: () => void;
}

export default function PipelineHUD({ quota: _quota, onLaunch }: PipelineHUDProps) {
  return (
    <div className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-6 z-10 shrink-0 shadow-sm">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-500">
        <span>AtomField</span>
        <span className="text-slate-300">/</span>
        <span>Prebuilt</span>
        <span className="text-slate-300">/</span>
        <span className="text-slate-900 font-bold">Nanoreactor Catalysis</span>
      </div>
      
      <div className="flex items-center gap-4">
        <div className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5 select-none">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Online
        </div>
        <button 
          onClick={onLaunch}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-bold rounded-lg shadow-md transition-all active:scale-95"
        >
          Launch Pipeline
        </button>
      </div>
    </div>
  );
}
