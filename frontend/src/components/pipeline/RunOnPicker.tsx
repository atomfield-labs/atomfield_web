import { useEffect, useState } from 'react';
import { ChevronDown, Server } from 'lucide-react';
import { targetsService } from '../../api/services';
import type { ComputeTarget } from '../../types/api';
import AddClusterModal from './AddClusterModal';

// Refresh the online dots this often while the editor is open.
const REFRESH_MS = 30000;
const ADD_CLUSTER = '__add_cluster__';

const SELECT = [
  'h-10 pl-9 pr-8 rounded-[10px] border border-stone-200 bg-white',
  'text-sm text-stone-900 max-w-[16rem] appearance-none cursor-pointer',
  'hover:bg-stone-50 focus:outline-none focus:border-stone-400',
].join(' ');
const ICON = 'pointer-events-none absolute text-stone-500';

interface RunOnPickerProps {
  // The chosen target's id; null means the shared AtomField server.
  value: string | null;
  onChange: (targetId: string | null) => void;
}

/**
 * The label of a target in the list, with its online state.
 */
function label(target: ComputeTarget): string {
  const name = target.shared ? 'AtomField server' : target.name;
  return `${target.online ? '●' : '○'} ${name}`;
}

/**
 * Choose where a pipeline runs: the shared server, or one of your own
 * clusters (with a dot showing whether its agent is online).
 */
export default function RunOnPicker({ value, onChange }: RunOnPickerProps) {
  const [targets, setTargets] = useState<ComputeTarget[]>([]);
  const [isAdding, setIsAdding] = useState(false);

  // Load now and every REFRESH_MS; ignore answers that arrive after
  // the picker is gone.
  useEffect(() => {
    let ignore = false;
    const load = async () => {
      const list = await targetsService.list().catch(() => []);
      if (!ignore) setTargets(list);
    };
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      ignore = true;
      clearInterval(timer);
    };
  }, []);

  const choose = (chosen: string) => {
    if (chosen === ADD_CLUSTER) {
      setIsAdding(true);
      return;
    }
    const target = targets.find((item) => item.id === chosen);
    onChange(target && !target.shared ? target.id : null);
  };

  const selected =
    value ?? targets.find((target) => target.shared)?.id ?? '';

  return (
    <>
      <label className="relative flex items-center">
        <span className="sr-only">Run on</span>
        <Server size={16} aria-hidden="true" className={`${ICON} left-3`} />
        <select
          value={selected}
          onChange={(event) => choose(event.target.value)}
          title="Where this pipeline runs (● online, ○ offline)"
          className={SELECT}
        >
          {targets.map((target) => (
            <option key={target.id} value={target.id}>
              {label(target)}
            </option>
          ))}
          <option value={ADD_CLUSTER}>+ Add a cluster…</option>
        </select>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={`${ICON} right-3`}
        />
      </label>
      <AddClusterModal
        isOpen={isAdding}
        onClose={() => setIsAdding(false)}
        onPaired={(target) => {
          void targetsService.list().then(setTargets);
          onChange(target.id);
        }}
      />
    </>
  );
}
