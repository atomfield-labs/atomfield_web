// The little of the chart library the web app calls.
declare module 'plotly.js-basic-dist-min' {
  interface PlotlyApi {
    react(
      root: HTMLElement,
      data: object[],
      layout: object,
      config: object
    ): Promise<unknown>;
    purge(root: HTMLElement): void;
  }
  const Plotly: PlotlyApi;
  export default Plotly;
}
