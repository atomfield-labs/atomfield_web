// A script's plots (<job>_plots.json; see docs/releases.md): what to
// show, not how to draw it. A null in a line leaves a gap.
export type PlotValue = number | null;

export interface AxisSpec {
  label?: string;
  // Named places along the axis, e.g. the special points of a path.
  ticks?: [number, string][];
  range?: [number, number];
  log?: boolean;
  // Where thin guide lines cross this axis, each with its name if it
  // isn't plain what the line is.
  lines?: (number | [number, string])[];
}

export interface CurveSpec {
  name: string;
  x: PlotValue[];
  // One line, or many drawn alike, e.g. the bands of a band structure.
  y: PlotValue[][];
  // What the tooltip calls each of many lines, e.g. "Band".
  hover?: string;
  // Starts switched off, for the legend to switch on.
  hidden?: boolean;
  // Wash the area between the line and zero on this axis.
  fill?: 'x' | 'y';
}

export interface BarsSpec {
  labels: string[];
  values: number[];
  // More to say about each bar, in the tooltip.
  hover?: string[];
}

export interface GraphNodeSpec {
  x: number;
  y: number;
  label: string;
  hover?: string;
}

export interface GraphSpec {
  nodes: GraphNodeSpec[];
  // Arrows, as positions in the node list.
  edges: [number, number][];
}

// Holds one of curves, bars or graph. Panels of a plot stand side by
// side and share the y axis.
export interface PanelSpec {
  width?: number;
  x?: AxisSpec;
  y?: AxisSpec;
  curves?: CurveSpec[];
  bars?: BarsSpec;
  graph?: GraphSpec;
}

export interface PlotSpec {
  title: string;
  panels: PanelSpec[];
}
