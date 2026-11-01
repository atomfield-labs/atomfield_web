import type {
  AxisSpec,
  BarsSpec,
  CurveSpec,
  GraphSpec,
  PanelSpec,
  PlotSpec,
} from '../types/plots';

/**
 * Turns a script's plots into figures for the chart library. Only the
 * fields named here pass through, and all text is made inert, so a file
 * can say what to show but nothing about how the page behaves. The look
 * lives here too, so every step's plots read as one system.
 */

const PLOTS_FORMAT = 1;

// Orange first; this order keeps neighbours apart for colour-blind
// readers. Curves past the eighth go gray rather than reuse a colour.
const SERIES_COLOURS = [
  '#ea580c',
  '#2a78d6',
  '#1baf7a',
  '#6250d6',
  '#e87ba4',
  '#008300',
  '#eda100',
  '#e34948',
];
const OTHER_COLOUR = '#94a3b8';
const SURFACE = '#ffffff';
const INK = '#334155';
const MUTED_INK = '#64748b';
const GRID = '#f1f5f9';
const AXIS_LINE = '#cbd5e1';
const GUIDE = '#94a3b8';
const FONT = "Inter, system-ui, Avenir, Helvetica, Arial, sans-serif";

const LINE_WIDTH = 2;
const THIN_LINE_WIDTH = 1.5;
// A curve of more lines than this is drawn thinner.
const FEW_LINES = 3;
const WASH_OPACITY = 0.1;
const PANEL_GAP = 0.03;
const NUMBER_FORMAT = '.5~g';
const MARGIN = { l: 12, r: 16, b: 12 };
const TOP_MARGIN = 12;
const TOP_MARGIN_WITH_LEGEND = 34;
const NODE_SIZE = 12;
// Bars stay this thin however few there are, on a chart about this wide.
const MAX_BAR_WIDTH = 32;
const TYPICAL_CHART_WIDTH = 780;
const MIN_BAR_GAP = 0.2;
// Past this, a graph's links are plain lines: arrows get slow.
const MAX_ARROWS = 200;

interface Figure {
  data: object[];
  layout: object;
}

/**
 * Read a plots file; null if it isn't one this page understands.
 */
export function parsePlots(text: string): PlotSpec[] | null {
  try {
    const file = JSON.parse(text);
    const known = file?.format === PLOTS_FORMAT && Array.isArray(file.plots);
    return known && file.plots.every(isPlot) ? file.plots : null;
  } catch {
    return null;
  }
}

function isPlot(plot: Partial<PlotSpec> | null): boolean {
  return (
    typeof plot?.title === 'string' &&
    Array.isArray(plot.panels) &&
    plot.panels.length > 0
  );
}

/**
 * Text the chart library shows as it is, never as markup.
 */
function inert(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function colourAt(index: number): string {
  return SERIES_COLOURS[index] ?? OTHER_COLOUR;
}

function washOf(colour: string): string {
  const channels = [1, 3, 5].map((at) =>
    parseInt(colour.slice(at, at + 2), 16)
  );
  return `rgba(${channels.join(',')},${WASH_OPACITY})`;
}

function axisLayout(axis: AxisSpec = {}, hidden = false): object {
  if (hidden) return { visible: false };
  const named = axis.ticks ?? [];
  return {
    title: {
      text: inert(axis.label ?? ''),
      font: { size: 12, color: INK },
      standoff: 8,
    },
    type: axis.log ? 'log' : 'linear',
    automargin: true,
    showline: true,
    linecolor: AXIS_LINE,
    gridcolor: named.length ? AXIS_LINE : GRID,
    zeroline: false,
    tickfont: { size: 11, color: MUTED_INK },
    exponentformat: 'power',
    hoverformat: NUMBER_FORMAT,
    ...(axis.range && {
      range: axis.log ? axis.range.map(Math.log10) : axis.range,
    }),
    ...(named.length > 0 && {
      tickmode: 'array',
      tickvals: named.map(([place]) => place),
      ticktext: named.map(([, label]) => inert(label)),
    }),
  };
}

const CROSSHAIR = {
  showspikes: true,
  spikemode: 'across',
  spikesnap: 'cursor',
  spikethickness: 1,
  spikedash: 'solid',
  spikecolor: AXIS_LINE,
};

/**
 * A guide line, with its name if it has one.
 */
function guideLine(
  guide: number | [number, string],
  place: (at: number) => object
): object {
  const [at, name] = Array.isArray(guide) ? guide : [guide, ''];
  return {
    type: 'line',
    ...place(at),
    line: { color: GUIDE, width: 1 },
    layer: 'below',
    label: {
      text: inert(name),
      textposition: 'end',
      yanchor: 'bottom',
      font: { size: 11, color: MUTED_INK },
    },
  };
}

function guideLines(
  panel: PanelSpec,
  xName: string,
  yName: string
): object[] {
  const across = (panel.x?.lines ?? []).map((guide) =>
    guideLine(guide, (at) => ({
      xref: xName,
      yref: `${yName} domain`,
      x0: at,
      x1: at,
      y0: 0,
      y1: 1,
    }))
  );
  const along = (panel.y?.lines ?? []).map((guide) =>
    guideLine(guide, (at) => ({
      xref: `${xName} domain`,
      yref: yName,
      x0: 0,
      x1: 1,
      y0: at,
      y1: at,
    }))
  );
  return [...across, ...along];
}

/**
 * The tooltip of a line: its value, and x too when no crosshair or
 * named place says where it is.
 */
function lineHover(
  panel: PanelSpec,
  label: string,
  unified: boolean
): string {
  const y = `%{y:${NUMBER_FORMAT}}`;
  const showsX = !unified && !panel.x?.ticks;
  const value = showsX ? `%{x:${NUMBER_FORMAT}}, ${y}` : y;
  return `${value}<extra>${inert(label)}</extra>`;
}

function curveTraces(
  curve: CurveSpec,
  index: number,
  panel: PanelSpec,
  xName: string,
  unified: boolean
): object[] {
  const colour = colourAt(index);
  const many = curve.y.length > 1;
  const width = curve.y.length > FEW_LINES ? THIN_LINE_WIDTH : LINE_WIDTH;
  return curve.y.map((values, line) => ({
    type: 'scatter',
    mode: 'lines',
    xaxis: xName,
    x: curve.x,
    y: values,
    name: inert(curve.name),
    legendgroup: inert(curve.name),
    showlegend: line === 0,
    visible: curve.hidden ? 'legendonly' : true,
    line: { color: colour, width, shape: 'linear' },
    fill: curve.fill ? `tozero${curve.fill}` : 'none',
    fillcolor: washOf(colour),
    hovertemplate: lineHover(
      panel,
      many ? `${curve.hover ?? curve.name} ${line + 1}` : curve.name,
      unified
    ),
  }));
}

function barTrace(bars: BarsSpec, xName: string): object {
  const notes = bars.hover?.map(inert);
  const note = notes ? '<br>%{customdata}' : '';
  return {
    type: 'bar',
    xaxis: xName,
    x: bars.labels.map(inert),
    y: bars.values,
    customdata: notes,
    marker: { color: colourAt(0), cornerradius: 4 },
    showlegend: false,
    hovertemplate: `%{y:${NUMBER_FORMAT}}${note}<extra>%{x}</extra>`,
  };
}

function graphTraces(graph: GraphSpec, xName: string): object[] {
  const { nodes, edges } = graph;
  const along = (axis: 'x' | 'y') =>
    edges.flatMap(([from, to]) => [nodes[from][axis], nodes[to][axis], null]);
  return [
    {
      type: 'scatter',
      mode: 'lines',
      xaxis: xName,
      x: along('x'),
      y: along('y'),
      line: { color: AXIS_LINE, width: 1 },
      hoverinfo: 'skip',
      showlegend: false,
    },
    {
      type: 'scatter',
      mode: 'markers+text',
      xaxis: xName,
      x: nodes.map((node) => node.x),
      y: nodes.map((node) => node.y),
      text: nodes.map((node) => inert(node.label)),
      textposition: 'top center',
      textfont: { size: 10, color: MUTED_INK },
      hovertext: nodes.map((node) => inert(node.hover ?? node.label)),
      hovertemplate: '%{hovertext}<extra></extra>',
      marker: {
        size: NODE_SIZE,
        color: colourAt(0),
        line: { width: 2, color: SURFACE },
      },
      showlegend: false,
    },
  ];
}

function graphArrows(graph: GraphSpec, xName: string): object[] {
  if (graph.edges.length > MAX_ARROWS) return [];
  return graph.edges.map(([from, to]) => ({
    xref: xName,
    yref: 'y',
    axref: xName,
    ayref: 'y',
    x: graph.nodes[to].x,
    y: graph.nodes[to].y,
    ax: graph.nodes[from].x,
    ay: graph.nodes[from].y,
    text: '',
    showarrow: true,
    arrowhead: 2,
    arrowwidth: 1,
    arrowcolor: GUIDE,
    standoff: NODE_SIZE / 2,
  }));
}

function panelTraces(
  panel: PanelSpec,
  xName: string,
  unified: boolean
): object[] {
  if (panel.graph) return graphTraces(panel.graph, xName);
  if (panel.bars) return [barTrace(panel.bars, xName)];
  return (panel.curves ?? []).flatMap((curve, index) =>
    curveTraces(curve, index, panel, xName, unified)
  );
}

/**
 * Where each panel stands across the plot, by its share of the width.
 */
function panelDomains(panels: PanelSpec[]): [number, number][] {
  const gaps = PANEL_GAP * (panels.length - 1);
  const total = panels.reduce((sum, panel) => sum + (panel.width ?? 1), 0);
  let start = 0;
  return panels.map((panel) => {
    const end = start + ((panel.width ?? 1) / total) * (1 - gaps);
    const domain: [number, number] = [start, end];
    start = end + PANEL_GAP;
    return domain;
  });
}

/**
 * The share of each bar's slot to leave empty.
 */
function barGap(panels: PanelSpec[]): number {
  const count = panels.reduce(
    (most, panel) => Math.max(most, panel.bars?.labels.length ?? 0),
    1
  );
  const slot = TYPICAL_CHART_WIDTH / count;
  return Math.max(MIN_BAR_GAP, 1 - MAX_BAR_WIDTH / slot);
}

function hasLegend(panels: PanelSpec[]): boolean {
  return panels.some((panel) => (panel.curves?.length ?? 0) > 1);
}

function baseLayout(panels: PanelSpec[], unified: boolean): object {
  const legend = hasLegend(panels);
  return {
    autosize: true,
    paper_bgcolor: SURFACE,
    plot_bgcolor: SURFACE,
    font: { family: FONT, size: 12, color: INK },
    margin: {
      ...MARGIN,
      t: legend ? TOP_MARGIN_WITH_LEGEND : TOP_MARGIN,
    },
    showlegend: legend,
    legend: {
      orientation: 'h',
      x: 0,
      y: 1,
      yanchor: 'bottom',
      font: { size: 11, color: INK },
    },
    hovermode: unified ? 'x unified' : 'closest',
    hoverdistance: unified ? -1 : 24,
    spikedistance: unified ? -1 : 0,
    hoverlabel: {
      bgcolor: SURFACE,
      bordercolor: AXIS_LINE,
      font: { family: FONT, size: 12, color: INK },
    },
    bargap: barGap(panels),
    dragmode: 'zoom',
  };
}

/**
 * One plot as the chart library wants it. Panels share the y axis: a
 * vertical zoom moves them together, a horizontal one only its own.
 */
export function toFigure(plot: PlotSpec): Figure {
  const { panels } = plot;
  // One crosshair and one tooltip per x make sense for one set of curves.
  const unified = panels.length === 1 && !!panels[0].curves;
  const domains = panelDomains(panels);
  const axes: Record<string, object> = {
    yaxis: axisLayout(panels[0].y, !!panels[0].graph),
  };
  const data: object[] = [];
  const shapes: object[] = [];
  const annotations: object[] = [];
  panels.forEach((panel, index) => {
    const number = index === 0 ? '' : String(index + 1);
    const xName = `x${number}`;
    axes[`xaxis${number}`] = {
      ...axisLayout(panel.x, !!panel.graph),
      domain: domains[index],
      anchor: 'y',
      ...(unified && CROSSHAIR),
      // Bars are named, even when their names look like numbers.
      ...(panel.bars && { type: 'category' }),
    };
    data.push(...panelTraces(panel, xName, unified));
    shapes.push(...guideLines(panel, xName, 'y'));
    if (panel.graph) annotations.push(...graphArrows(panel.graph, xName));
  });
  const layout = {
    ...baseLayout(panels, unified),
    ...axes,
    shapes,
    annotations,
  };
  return { data, layout };
}

/**
 * The chart's controls: hover, drag to zoom, double-click to reset,
 * and the camera icon, which saves the plot under its title.
 */
export function chartConfig(title: string): object {
  return {
    responsive: true,
    displaylogo: false,
    doubleClick: 'reset',
    modeBarButtons: [['toImage'], ['zoom2d', 'pan2d'], ['resetScale2d']],
    toImageButtonOptions: {
      format: 'png',
      scale: 2,
      filename: title.replace(/[^\w-]+/g, '_'),
    },
  };
}
