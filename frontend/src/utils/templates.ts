import type {
  BlueprintEdge,
  BlueprintNode,
  PipelineBlueprint,
  PipelineTemplate,
  TaskDefinition,
  TemplateStep,
  TemplateStructure,
} from '../types/api';
import { parseStructureFile } from './structureParser';
import { defaultParameterValues } from './taskCatalog';

interface Position {
  x: number;
  y: number;
}

// Nodes go left to right in running order, one column per step.
const ORIGIN: Position = { x: 80, y: 220 };
const COLUMN_WIDTH = 224;
const ROW_HEIGHT = 180;

/**
 * Where each node of a template sits: structures in the first column,
 * each step one column right of the furthest node it follows, nodes
 * sharing a column stacked downwards. Steps come in running order, so
 * whatever a step follows is already placed.
 */
export function layoutTemplate(
  template: PipelineTemplate
): Map<string, Position> {
  const columns = new Map<string, number>();
  for (const structure of template.structures) columns.set(structure.key, 0);
  for (const step of template.steps) {
    const before = step.after.map((key) => columns.get(key) ?? 0);
    columns.set(step.key, Math.max(-1, ...before) + 1);
  }
  const rows = new Map<number, number>();
  const positions = new Map<string, Position>();
  for (const [key, column] of columns) {
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    positions.set(key, {
      x: ORIGIN.x + column * COLUMN_WIDTH,
      y: ORIGIN.y + row * ROW_HEIGHT,
    });
  }
  return positions;
}

/**
 * A template's example structure as a canvas node, described as an
 * uploaded file is; its text goes with the run on deploy.
 */
function structureNode(
  structure: TemplateStructure,
  position: Position
): BlueprintNode {
  return {
    ...parseStructureFile(structure.filename, structure.content),
    ui_id: structure.key,
    id: structure.key,
    type: 'structure',
    raw_content: structure.content,
    workspace_path: `/workspace/${structure.filename}`,
    position,
  };
}

/**
 * A template step as a canvas node, every setting shown: the task's
 * defaults, then the template's values over them.
 */
function stepNode(
  step: TemplateStep,
  task: TaskDefinition | undefined,
  position: Position
): BlueprintNode {
  const parameters = {
    ...(task ? defaultParameterValues(task) : {}),
    ...step.parameters,
  };
  return {
    ui_id: step.key,
    id: step.key,
    type: 'default',
    script_name: step.task,
    label: step.label,
    status: 'Ready',
    parameters,
    default_parameters: parameters,
    inputs: {},
    position,
  };
}

/**
 * A template as the canvas loads it: its nodes laid out in running
 * order, and an edge from every node a step follows.
 */
export function templateToBlueprint(
  template: PipelineTemplate,
  taskById: Map<string, TaskDefinition>
): PipelineBlueprint {
  const positions = layoutTemplate(template);
  const at = (key: string) => positions.get(key) ?? ORIGIN;
  const nodes = [
    ...template.structures.map((item) => structureNode(item, at(item.key))),
    ...template.steps.map((step) =>
      stepNode(step, taskById.get(step.task), at(step.key))
    ),
  ];
  const edges: BlueprintEdge[] = template.steps.flatMap((step) =>
    step.after.map((key) => ({
      id: `e-${key}-${step.key}`,
      upstream_ui_id: key,
      downstream_ui_id: step.key,
    }))
  );
  return { nodes, edges };
}
