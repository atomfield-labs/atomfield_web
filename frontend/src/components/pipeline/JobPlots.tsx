import { useEffect, useRef, useState } from 'react';
import { jobsService } from '../../api/services';
import { useJobFiles } from '../../hooks/useJobFiles';
import type { PlotSpec } from '../../types/plots';
import { chartConfig, parsePlots, toFigure } from '../../utils/plotFigure';
import { sharedRequest } from '../../utils/sharedRequest';

// A big library: fetched only when a plot is first opened.
const loadChartLibrary = sharedRequest(() =>
  import('plotly.js-basic-dist-min').then((library) => library.default)
);

const MUTED = 'text-xs text-slate-400';
const CHOICE = [
  'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
  'cursor-pointer',
].join(' ');
const CHOICE_IDLE = 'text-slate-500 hover:text-orange-600';
const CHOICE_ACTIVE = 'bg-orange-50 text-orange-600';
const UNREADABLE =
  "These plots can't be shown. Their numbers are in Artifacts.";

type ChartState = 'loading' | 'drawn' | 'failed';

/**
 * One plot, drawn when the chart library has arrived.
 */
function PlotChart({ plot }: { plot: PlotSpec }) {
  const root = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<ChartState>('loading');

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    let active = true;
    const draw = async () => {
      const library = await loadChartLibrary();
      if (!active) return;
      const { data, layout } = toFigure(plot);
      await library.react(element, data, layout, chartConfig(plot.title));
      if (active) setState('drawn');
    };
    draw().catch(() => active && setState('failed'));
    return () => {
      active = false;
      void loadChartLibrary().then((library) => library.purge(element));
    };
  }, [plot]);

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={root}
        className="w-full h-full"
      />
      {state !== 'drawn' && (
        <p className={`absolute inset-0 ${MUTED}`}>
          {state === 'failed' ? UNREADABLE : 'Loading...'}
        </p>
      )}
    </div>
  );
}

interface PlotPickerProps {
  plots: PlotSpec[];
  shown: PlotSpec;
  onChoose: (plot: PlotSpec) => void;
}

/**
 * What a step's plots are called: a plain title for one, a row of
 * buttons for several.
 */
function PlotPicker({ plots, shown, onChoose }: PlotPickerProps) {
  const lookOf = (plot: PlotSpec) =>
    plot === shown ? CHOICE_ACTIVE : CHOICE_IDLE;
  if (plots.length === 1) {
    return (
      <p className="px-2.5 py-1 text-xs font-medium text-slate-600">
        {shown.title}
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-1">
      {plots.map((plot) => (
        <button
          key={plot.title}
          type="button"
          className={`${CHOICE} ${lookOf(plot)}`}
          onClick={() => onChoose(plot)}
        >
          {plot.title}
        </button>
      ))}
    </div>
  );
}

interface JobPlotsProps {
  jobId: string | undefined;
  status: string | undefined;
}

interface LoadedPlots {
  source: string;
  plots: PlotSpec[] | null;
}

/**
 * The plots a step's script left, drawn from its numbers.
 */
export default function JobPlots({ jobId, status }: JobPlotsProps) {
  const { files } = useJobFiles(jobId, status);
  const name = files.find((file) => file.kind === 'plots')?.name;
  const source = `${jobId}/${name}`;
  const [loaded, setLoaded] = useState<LoadedPlots | null>(null);
  const [chosen, setChosen] = useState<PlotSpec | null>(null);

  useEffect(() => {
    if (!jobId || !name) return;
    let active = true;
    jobsService
      .readJobFile(jobId, name)
      .then((text) => active && setLoaded({ source, plots: parsePlots(text) }))
      .catch(() => active && setLoaded({ source, plots: null }));
    return () => {
      active = false;
    };
  }, [jobId, name, source]);

  if (!name) return <p className={MUTED}>No plots yet.</p>;
  if (loaded?.source !== source) return <p className={MUTED}>Loading...</p>;
  if (!loaded.plots) return <p className={MUTED}>{UNREADABLE}</p>;

  const shown =
    chosen && loaded.plots.includes(chosen) ? chosen : loaded.plots[0];
  return (
    <div className="h-full flex flex-col gap-2 min-h-0">
      <PlotPicker
        plots={loaded.plots}
        shown={shown}
        onChoose={setChosen}
      />
      <PlotChart
        key={shown.title}
        plot={shown}
      />
    </div>
  );
}
