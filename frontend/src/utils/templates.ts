import type { PipelineBlueprint, TaskDefinition } from '../types/api';
import { defaultParameterValues } from './taskCatalog';

/**
 * A template with every task's settings filled in: the catalog's
 * defaults first, then the values the template sets. Templates name
 * only what they change, and the inspector still shows every setting,
 * as for a task dragged from the palette.
 */
export function withCatalogDefaults(
  blueprint: PipelineBlueprint,
  taskById: Map<string, TaskDefinition>
): PipelineBlueprint {
  const nodes = blueprint.nodes.map((node) => {
    const task = taskById.get(node.script_name ?? '');
    if (!task) return node;
    const parameters = {
      ...defaultParameterValues(task),
      ...(node.parameters ?? {}),
    };
    return { ...node, parameters, default_parameters: parameters };
  });
  return { ...blueprint, nodes };
}
