import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  GripVertical,
  Info,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  X,
} from 'lucide-react';
import { usePipelineTemplates } from '../../hooks/usePipelineTemplates';
import { useTaskDefinitions } from '../../hooks/useTaskDefinitions';
import type { PipelineTemplate, TaskDefinition } from '../../types/api';
import { groupByCategory } from '../../utils/taskCatalog';

interface SidebarItem {
  id: string;
  title: string;
  description: string;
  // The input-file box, rather than a task.
  isInput?: boolean;
  task?: TaskDefinition;
  // A ready-made pipeline: all its steps, linked.
  template?: PipelineTemplate;
}

interface TaskGroup {
  id: string;
  label: string;
  items: SidebarItem[];
}

interface TooltipState {
  item: SidebarItem;
  top: number;
  left: number;
}

// What a pipeline starts from: a file, dropped on its box.
const INPUTS: TaskGroup = {
  id: 'inputs',
  label: 'Inputs',
  items: [
    {
      id: 'input_files',
      title: 'Input files',
      description:
        'A file the pipeline starts from. Drag it onto the canvas, then ' +
        'drop a file on it.',
      isInput: true,
    },
  ],
};
// The catalog's group for ready-to-run tasks. Ready-made pipelines join
// it here, so it takes the broader name.
const PREBUILT_CATEGORY = 'Prebuilt Drivers';
const PREBUILT_LABEL = 'Prebuilt Workflows';
// The ready-made pipelines offered in this list; the start screen has all.
const LISTED_TEMPLATES = new Set(['ahc']);
const TOOLTIP_HEIGHT = 110;
const TOOLTIP_GAP = 10;
const PANEL = [
  'relative bg-white border-r border-stone-200 flex flex-col shrink-0',
  'select-none z-20 transition-all duration-300 ease-in-out',
].join(' ');
const ITEM = [
  'flex items-start gap-1.5 py-1.5 px-2.5 rounded-lg',
  'text-sm leading-snug text-stone-900 hover:text-orange-600 cursor-grab',
  'active:cursor-grabbing',
].join(' ');
// What can be dragged has a handle, so a name is not taken for a header.
const GRIP = 'shrink-0 mt-[3px] text-stone-300';
const GROUP = 'py-2 border-t border-stone-200 first:border-t-0 first:pt-0';
const OPEN_BUTTON = [
  'absolute top-3 left-3 z-30 h-9 px-3 flex items-center gap-2 rounded-lg',
  'bg-white border border-stone-200 text-sm text-stone-700',
  'hover:bg-stone-50 cursor-pointer',
].join(' ');
const ICON_BUTTON = [
  'p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100',
  'cursor-pointer',
].join(' ');
const SEARCH_BOX = [
  'flex-1 min-w-0 flex items-center gap-2 h-10 px-3 rounded-[10px]',
  'bg-stone-100',
].join(' ');
const SEARCH_INPUT = [
  'flex-1 w-full min-w-0 bg-transparent text-sm text-stone-900',
  'outline-none',
].join(' ');
const GROUP_BUTTON = [
  'w-full flex items-center justify-between py-1 px-2.5 rounded-md',
  'text-stone-500 text-[11px] font-semibold tracking-wider uppercase',
  'enabled:hover:text-stone-800 transition-colors cursor-pointer',
  'disabled:cursor-default select-none',
].join(' ');
const INFO_BUTTON = 'shrink-0 mt-[3px] text-stone-300 hover:text-stone-500';
const TOOLTIP = [
  'fixed z-50 pointer-events-none w-64 p-3 rounded-lg bg-stone-900/95',
  'text-white text-xs shadow-xl',
].join(' ');

function taskItem(task: TaskDefinition): SidebarItem {
  return {
    id: task.id,
    title: task.title,
    description: task.description,
    task,
  };
}

function templateItem(template: PipelineTemplate): SidebarItem {
  return {
    id: `template:${template.id}`,
    title: template.title,
    description: template.description,
    template,
  };
}

/**
 * Inputs first, then one group per catalog category, the prebuilt one
 * also holding the listed ready-made pipelines.
 */
function taskGroups(
  tasks: TaskDefinition[],
  templates: PipelineTemplate[]
): TaskGroup[] {
  const listed = templates
    .filter((template) => LISTED_TEMPLATES.has(template.id))
    .map(templateItem);
  const categories = groupByCategory(tasks);
  const catalog = categories.map(([label, group]) => {
    const prebuilt = label === PREBUILT_CATEGORY;
    return {
      id: `catalog:${label}`,
      label: prebuilt ? PREBUILT_LABEL : label,
      items: [...group.map(taskItem), ...(prebuilt ? listed : [])],
    };
  });
  const hasPrebuilt = categories.some(([label]) => label === PREBUILT_CATEGORY);
  const ownGroup =
    hasPrebuilt || listed.length === 0
      ? []
      : [{ id: 'catalog:prebuilt', label: PREBUILT_LABEL, items: listed }];
  return [INPUTS, ...catalog, ...ownGroup];
}

/**
 * The groups with only the items matching a search; empty groups go.
 */
function matching(groups: TaskGroup[], query: string): TaskGroup[] {
  if (!query) return groups;
  const fits = (item: SidebarItem) =>
    `${item.title} ${item.description}`.toLowerCase().includes(query);
  return groups
    .map((group) => ({ ...group, items: group.items.filter(fits) }))
    .filter((group) => group.items.length > 0);
}

/**
 * What a drag onto the canvas carries: the input-file box, a task, or a
 * ready-made pipeline.
 */
function dragPayload(item: SidebarItem) {
  if (item.isInput) return { type: 'structure', title: 'Structure Input' };
  if (item.template) {
    return { type: 'template', title: item.title, template: item.template };
  }
  return item.task;
}

function startDrag(event: React.DragEvent, item: SidebarItem): void {
  const payload = dragPayload(item);
  if (!payload) return;
  event.dataTransfer.setData('application/reactflow', JSON.stringify(payload));
  event.dataTransfer.setData('scriptName', payload.title);
  event.dataTransfer.effectAllowed = 'move';
}

/**
 * The tasks a pipeline is built from, and ready-made pipelines,
 * searchable and grouped by category; drag one onto the canvas to add it.
 */
export default function LeftSidebar() {
  const { tasks, isLoading } = useTaskDefinitions();
  const templates = usePipelineTemplates();
  const [query, setQuery] = useState('');
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 768
  );
  // Groups start open; only the ones a person closes are recorded.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const searchText = query.trim().toLowerCase();
  const searching = searchText !== '';
  const groups = matching(taskGroups(tasks, templates), searchText);

  const toggleGroup = (groupId: string) => {
    setOpenGroups((prev) => ({
      ...prev,
      [groupId]: !(prev[groupId] ?? true),
    }));
  };

  const showTooltip = (event: React.MouseEvent, item: SidebarItem) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const lowest = window.innerHeight - TOOLTIP_HEIGHT - 16;
    const top = Math.min(rect.top, lowest);
    setTooltip({ item, top, left: rect.right + TOOLTIP_GAP });
  };

  return (
    <>
      {isCollapsed && (
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          className={OPEN_BUTTON}
          aria-label="Show tasks"
        >
          <PanelLeftOpen size={16} className="text-stone-500" />
          Tasks
        </button>
      )}

      <aside
        className={`${PANEL} ${
          isCollapsed ? 'w-0 border-r-0 overflow-hidden' : 'w-[248px]'
        }`}
      >
        <div className="w-[248px] h-full flex flex-col p-3 gap-3">
          <div className="flex items-center gap-1.5">
            <label className={SEARCH_BOX}>
              <Search size={16} className="shrink-0 text-stone-500" />
              <span className="sr-only">Search tasks</span>
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search tasks"
                className={SEARCH_INPUT}
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="text-stone-400 hover:text-stone-600 cursor-pointer"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </label>
            <button
              type="button"
              onClick={() => setIsCollapsed(true)}
              className={ICON_BUTTON}
              aria-label="Hide tasks"
            >
              <PanelLeftClose size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto -mx-1 px-1">
            {isLoading ? (
              <p className="py-8 text-center text-sm text-stone-400">
                Loading tasks…
              </p>
            ) : groups.length === 0 ? (
              <p className="py-8 text-center text-sm text-stone-400">
                No task matches.
              </p>
            ) : (
              groups.map((group) => {
                const isOpen = searching || (openGroups[group.id] ?? true);
                const Chevron = isOpen ? ChevronDown : ChevronRight;
                return (
                  <section key={group.id} className={GROUP}>
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      disabled={searching}
                      aria-expanded={isOpen}
                      className={GROUP_BUTTON}
                    >
                      <span>{group.label}</span>
                      <Chevron className="w-3.5 h-3.5" />
                    </button>
                    {isOpen && (
                      <div className="mt-1 space-y-0.5">
                        {group.items.map((item) => (
                          <div
                            key={item.id}
                            draggable
                            onDragStart={(event) => startDrag(event, item)}
                            className={ITEM}
                          >
                            <GripVertical
                              size={14}
                              aria-hidden="true"
                              className={GRIP}
                            />
                            <span
                              title={item.title}
                              className="flex-1 min-w-0 line-clamp-2"
                            >
                              {item.title}
                            </span>
                            <button
                              type="button"
                              onMouseEnter={(event) =>
                                showTooltip(event, item)
                              }
                              onMouseLeave={() => setTooltip(null)}
                              className={INFO_BUTTON}
                              aria-label={`About ${item.title}`}
                            >
                              <Info size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                );
              })
            )}
          </div>
        </div>
      </aside>

      {tooltip && (
        <div
          className={TOOLTIP}
          style={{ top: tooltip.top, left: tooltip.left }}
        >
          <div className="mb-1 font-semibold">{tooltip.item.title}</div>
          <div className="leading-relaxed text-stone-300">
            {tooltip.item.description}
          </div>
        </div>
      )}
    </>
  );
}
