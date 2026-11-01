import type {
  ParameterValue,
  TaskDefinition,
} from '../types/api';

// Categories shown first in the palette; any others follow, sorted.
const CATEGORY_ORDER = [
  'Optimizers',
  'Molecular Dynamics',
  'Materials Informatics',
];

// Keys the platform sets itself; older drafts stored them as parameters.
const PLATFORM_KEYS = new Set(['input', 'jobname']);

/**
 * Every parameter of a task with its default value, in catalog order.
 */
export function defaultParameterValues(
  task: TaskDefinition
): Record<string, ParameterValue> {
  return Object.fromEntries(
    task.parameters.map((spec) => [spec.name, spec.default])
  );
}

/**
 * The first input port that accepts a file's extension, or null.
 */
export function inputPortForFile(
  task: TaskDefinition,
  filename: string
): string | null {
  const extension = filename.split('.').pop()?.toLowerCase() ?? '';
  const port = task.inputs.find((item) => item.formats.includes(extension));
  return port ? port.name : null;
}

/**
 * Tasks grouped by category, preferred categories first.
 */
export function groupByCategory(
  tasks: TaskDefinition[]
): Array<[string, TaskDefinition[]]> {
  const groups = new Map<string, TaskDefinition[]>();
  for (const task of tasks) {
    groups.set(task.category, [...(groups.get(task.category) ?? []), task]);
  }
  const rank = (name: string) => {
    const index = CATEGORY_ORDER.indexOf(name);
    return index === -1 ? CATEGORY_ORDER.length : index;
  };
  return [...groups.entries()].sort(
    ([a], [b]) => rank(a) - rank(b) || a.localeCompare(b)
  );
}

/**
 * The values to send for a step: only what its task still takes, so a
 * draft saved earlier still submits after its task file hides or drops
 * a parameter. Without a task, only what the platform now sets itself
 * (job name, input files) is dropped.
 */
export function currentParameters(
  task: TaskDefinition | undefined,
  parameters: Record<string, unknown>
): Record<string, unknown> {
  const taken = task && new Set(task.parameters.map((spec) => spec.name));
  return Object.fromEntries(
    Object.entries(parameters).filter(([key]) =>
      taken ? taken.has(key) : !PLATFORM_KEYS.has(key)
    )
  );
}
