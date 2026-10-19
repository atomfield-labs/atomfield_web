import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Info } from 'lucide-react';
import { scriptsService } from '../../api/services';
import type { ScriptManifestItem } from '../../types/api';

export type { ScriptManifestItem };

interface LeftSidebarProps {
  onLoadModularWorkflow?: () => void;
  onLoadFlashWorkflow?: () => void;
}

interface SidebarItem {
  id: string;
  title: string;
  filename?: string;
  description: string;
  isStructure?: boolean;
  isWorkflow?: boolean;
  workflowType?: 'flash' | 'pipe';
  rawScript?: ScriptManifestItem;
}

interface CategoryDefinition {
  id: string;
  label: string;
  getItems: (
    scripts: ScriptManifestItem[],
    onLoadModularWorkflow?: () => void,
    onLoadFlashWorkflow?: () => void
  ) => SidebarItem[];
}

const CATEGORIES: CategoryDefinition[] = [
  {
    id: 'builders',
    label: 'Builders',
    getItems: () => [
      {
        id: 'structure_input',
        title: 'Structure Input (.xyz)',
        description: 'Molecular coordinate file input (.xyz, .mol, .sdf, .pdb). Drag onto canvas or upload file.',
        isStructure: true,
      },
    ],
  },
  {
    id: 'optimizers',
    label: 'Optimizers',
    getItems: (scripts) => {
      const targetIds = ['xtb_opt', 'mlff_opt', 'mlff_refine', 'ts_search'];
      return targetIds
        .map((id) => scripts.find((s) => s.id === id))
        .filter((s): s is ScriptManifestItem => !!s)
        .map((s) => ({
          id: s.id,
          title: s.title,
          filename: s.filename,
          description: s.description,
          rawScript: s,
        }));
    },
  },
  {
    id: 'scfs',
    label: 'SCFs',
    getItems: () => [], // Dedicated single-point SCF drivers coming soon
  },
  {
    id: 'molecular_dynamics',
    label: 'Molecular Dynamics',
    getItems: (scripts) => {
      const targetIds = ['xtb_md'];
      return targetIds
        .map((id) => scripts.find((s) => s.id === id))
        .filter((s): s is ScriptManifestItem => !!s)
        .map((s) => ({
          id: s.id,
          title: s.title,
          filename: s.filename,
          description: s.description,
          rawScript: s,
        }));
    },
  },
  {
    id: 'materials_informatics',
    label: 'Materials Informatics',
    getItems: (scripts) => {
      const targetIds = ['rxn_network'];
      return targetIds
        .map((id) => scripts.find((s) => s.id === id))
        .filter((s): s is ScriptManifestItem => !!s)
        .map((s) => ({
          id: s.id,
          title: s.title,
          filename: s.filename,
          description: s.description,
          rawScript: s,
        }));
    },
  },
  {
    id: 'prebuilt_drivers',
    label: 'Prebuilt Drivers',
    getItems: (_scripts, _onLoadModularWorkflow, _onLoadFlashWorkflow) => {
      const items: SidebarItem[] = [];

      items.push({
        id: 'flash_nanoreactor',
        title: 'Nanoreactor Flash',
        filename: 'xtb_nanoreactor.py',
        description: 'Fast monolithic prebuilt run: parallel MD replicates & reaction network graph extraction. Click to switch pipeline.',
        isWorkflow: true,
        workflowType: 'flash',
      });

      items.push({
        id: 'modular_nanoreactor',
        title: 'Nanoreactor Pipe',
        filename: 'modular_workflow',
        description: '2D decomposed 5-node reaction discovery pipeline: xTB Opt -> xTB MD -> Reaction Network -> SevenNet Refine -> TS Search. Click to switch pipeline.',
        isWorkflow: true,
        workflowType: 'pipe',
      });

      return items;
    },
  },
];

interface TooltipState {
  item: SidebarItem;
  top: number;
  left: number;
}

export default function LeftSidebar({
  onLoadModularWorkflow,
  onLoadFlashWorkflow,
}: LeftSidebarProps = {}) {
  const [scripts, setScripts] = useState<ScriptManifestItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    builders: true,
    optimizers: true,
    scfs: false,
    molecular_dynamics: true,
    materials_informatics: true,
    prebuilt_drivers: true,
  });

  useEffect(() => {
    scriptsService
      .getAvailableScripts()
      .then((data) => {
        setScripts(data);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch available scripts:', err);
        setIsLoading(false);
      });
  }, []);

  const toggleCategory = (catId: string) => {
    setOpenCategories((prev) => ({
      ...prev,
      [catId]: !prev[catId],
    }));
  };

  const onDragStart = (event: React.DragEvent, item: SidebarItem) => {
    if (item.isStructure) {
      event.dataTransfer.setData(
        'application/reactflow',
        JSON.stringify({ type: 'structure', title: 'Structure Input' })
      );
      event.dataTransfer.setData('scriptName', 'Structure Input');
      event.dataTransfer.effectAllowed = 'move';
      return;
    }

    if (item.isWorkflow && onLoadModularWorkflow) {
      onLoadModularWorkflow();
      return;
    }

    if (item.rawScript) {
      event.dataTransfer.setData('application/reactflow', JSON.stringify(item.rawScript));
      event.dataTransfer.setData('scriptName', item.rawScript.title);
      event.dataTransfer.effectAllowed = 'move';
    }
  };

  const handleInfoEnter = (event: React.MouseEvent, item: SidebarItem) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const tooltipEstimatedHeight = 110;
    const top = Math.min(rect.top, window.innerHeight - tooltipEstimatedHeight - 16);
    const left = rect.right + 10;
    setTooltip({ item, top, left });
  };

  const handleInfoLeave = () => {
    setTooltip(null);
  };

  return (
    <>
      <aside className="w-[260px] bg-white border-r border-slate-200 flex flex-col justify-between shrink-0 select-none z-10 shadow-xs">
        {/* Header and Scrollable Category List */}
        <div className="flex-1 overflow-y-auto p-3">
          <div className="flex items-center justify-between mb-3 px-1">
            <h2 className="text-[11px] font-bold text-slate-400 tracking-wider uppercase">
              Node Palette
            </h2>
            <span className="text-[10px] font-mono text-slate-400">
              {scripts.length} scripts
            </span>
          </div>

          {isLoading ? (
            <div className="py-8 text-center text-xs font-medium text-slate-400 animate-pulse">
              Loading library...
            </div>
          ) : (
            <div className="space-y-2">
              {CATEGORIES.map((cat) => {
                const items = cat.getItems(scripts, onLoadModularWorkflow, onLoadFlashWorkflow);
                const isOpen = !!openCategories[cat.id];

                return (
                  <div key={cat.id} className="mb-2">
                    {/* Collapsible Header in Soft Theme-Matched Light Orange */}
                    <button
                      type="button"
                      onClick={() => toggleCategory(cat.id)}
                      className="w-full flex items-center justify-between py-1.5 px-2.5 text-xs font-semibold bg-orange-50/90 hover:bg-orange-100 text-orange-600 border border-orange-200/80 rounded-md transition-colors select-none group"
                    >
                      <span className="text-[11px] font-bold tracking-wide uppercase text-orange-600 group-hover:text-orange-700">
                        {cat.label}
                      </span>
                      <div className="flex items-center gap-1.5 text-orange-600">
                        {items.length > 0 && (
                          <span className="text-[10px] font-mono font-bold bg-orange-200/60 text-orange-700 px-1.5 py-0.5 rounded">
                            {items.length}
                          </span>
                        )}
                        {isOpen ? (
                          <ChevronDown className="w-3.5 h-3.5 text-orange-600 group-hover:text-orange-700" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-orange-600 group-hover:text-orange-700" />
                        )}
                      </div>
                    </button>

                    {/* Collapsible Content with Light Orange Hover Strips */}
                    {isOpen && (
                      <div className="mt-1 space-y-0.5 pl-0.5 pr-0.5">
                        {items.length === 0 ? (
                          <div className="py-1 px-2.5 text-[11px] text-slate-400 italic">
                            Coming soon
                          </div>
                        ) : (
                          items.map((item) => (
                            <div
                              key={item.id}
                              draggable={!item.isWorkflow}
                              onDragStart={(e) => {
                                if (!item.isWorkflow) {
                                  onDragStart(e, item);
                                }
                              }}
                              onClick={() => {
                                if (item.isWorkflow) {
                                  if (item.workflowType === 'flash' && onLoadFlashWorkflow) {
                                    onLoadFlashWorkflow();
                                  } else if (item.workflowType === 'pipe' && onLoadModularWorkflow) {
                                    onLoadModularWorkflow();
                                  }
                                }
                              }}
                              className={`group flex items-center justify-between px-2.5 py-1.5 rounded text-xs text-slate-700 hover:text-blue-950 hover:bg-blue-50/80 border border-transparent hover:border-blue-200/80 transition-colors select-none ${
                                item.isWorkflow
                                  ? 'cursor-pointer active:bg-blue-100/70 font-medium'
                                  : 'cursor-grab active:cursor-grabbing font-medium'
                              }`}
                            >
                              <div className="flex items-center gap-1.5 truncate">
                                {item.isWorkflow && (
                                  <span className="w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0" />
                                )}
                                <span className="truncate text-[11.5px] leading-snug">
                                  {item.title}
                                </span>
                              </div>

                              <button
                                type="button"
                                onMouseEnter={(e) => handleInfoEnter(e, item)}
                                onMouseLeave={handleInfoLeave}
                                className="text-slate-400 hover:text-blue-600 p-0.5 rounded opacity-40 group-hover:opacity-100 transition-opacity ml-1.5 shrink-0"
                                aria-label="Details"
                              >
                                <Info className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Minimal Bottom Status Hint */}
        <div className="p-3 border-t border-slate-100">
          <div className="text-[11px] text-slate-400 leading-normal">
            Drag node to canvas to insert into pipeline.
          </div>
        </div>
      </aside>

      {/* Floating Hover Tooltip (Portaled / Fixed to prevent sidebar clipping) */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none w-64 p-3 bg-slate-900/95 text-white rounded-lg shadow-xl border border-slate-700/80 backdrop-blur-xs text-xs"
          style={{ top: tooltip.top, left: tooltip.left }}
        >
          <div className="font-semibold text-white mb-0.5 text-xs">
            {tooltip.item.title}
          </div>
          {tooltip.item.filename && (
            <div className="font-mono text-[10px] text-slate-400 mb-1.5">
              {tooltip.item.filename}
            </div>
          )}
          <div className="text-slate-300 text-[11px] leading-relaxed">
            {tooltip.item.description}
          </div>
        </div>
      )}
    </>
  );
}
