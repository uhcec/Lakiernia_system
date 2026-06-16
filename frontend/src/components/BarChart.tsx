export interface BarChartPoint {
  /** Stable key (e.g. ISO date) used for React keys. */
  key: string;
  /** Short axis tick, e.g. day-of-month "16". */
  tick: string;
  /** Full human label for the tooltip, e.g. "16.06.2026". */
  label: string;
  value: number;
}

interface BarChartProps {
  title: string;
  /** Unit shown next to values, e.g. "m²" or "szt.". */
  unit: string;
  data: BarChartPoint[];
  /** Tailwind background class for bars, e.g. "bg-accent". */
  barClassName?: string;
  /** Decimal places for displayed values. */
  decimals?: number;
  /** Fixed top of the Y axis. When omitted, the axis auto-scales to the data. */
  yMax?: number;
  /** Gridline/label interval on the Y axis (requires yMax). */
  yTickStep?: number;
  /** Plot area height in px (default 176). Increase for denser Y gridlines. */
  plotHeight?: number;
}

const DEFAULT_PLOT_HEIGHT_PX = 176; // h-44

function formatValue(value: number, decimals: number): string {
  return value.toLocaleString("pl-PL", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function BarChart({
  title,
  unit,
  data,
  barClassName = "bg-accent",
  decimals = 0,
  yMax,
  yTickStep,
  plotHeight = DEFAULT_PLOT_HEIGHT_PX,
}: BarChartProps) {
  const maxValue = data.reduce((max, point) => Math.max(max, point.value), 0);
  const total = data.reduce((sum, point) => sum + point.value, 0);
  const hasData = total > 0;

  // Either use a caller-fixed axis (with gridlines) or auto-scale to the data.
  const axisMax = yMax && yMax > 0 ? yMax : maxValue;
  const tickValues =
    yMax && yMax > 0 && yTickStep && yTickStep > 0
      ? Array.from({ length: Math.floor(yMax / yTickStep) + 1 }, (_, i) => yMax - i * yTickStep)
      : null;

  // Show every day's tick for a month-sized range; only thin out very dense ranges.
  const tickStep = data.length > 45 ? Math.ceil(data.length / 30) : 1;

  return (
    <div className="rounded-3xl border border-line bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.1em] text-steel">{title}</h3>
        <span className="text-sm font-semibold text-ink">
          {formatValue(total, decimals)} <span className="text-xs font-normal text-steel">{unit}</span>
        </span>
      </div>

      {hasData ? (
        <div className="flex gap-2">
          {/* Y axis labels: top value down to 0. */}
          <div
            className="flex flex-col justify-between py-0.5 text-right text-[10px] tabular-nums text-steel"
            style={{ height: plotHeight }}
          >
            {tickValues ? (
              tickValues.map((value) => <span key={value}>{formatValue(value, 0)}</span>)
            ) : (
              <>
                <span>{formatValue(maxValue, decimals)}</span>
                <span>0</span>
              </>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="relative" style={{ height: plotHeight }}>
              {/* Gridlines (one per Y tick) behind the bars. */}
              {tickValues ? (
                <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
                  {tickValues.map((value) => (
                    <div key={value} className="border-t border-dashed border-line/70" />
                  ))}
                </div>
              ) : null}

              <div className="relative flex h-full gap-px">
                {data.map((point) => {
                  const heightPercent = axisMax > 0 ? Math.min((point.value / axisMax) * 100, 100) : 0;
                  return (
                    <div key={point.key} className="group relative flex h-full min-w-0 flex-1 items-end justify-center">
                      {/* Tooltip */}
                      <div className="pointer-events-none absolute bottom-full z-10 mb-1 hidden -translate-y-0 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-[11px] font-medium text-white shadow-lg group-hover:block">
                        {point.label}: {formatValue(point.value, decimals)} {unit}
                      </div>
                      <div
                        className={[
                          "w-full rounded-t-sm transition group-hover:brightness-110",
                          point.value > 0 ? barClassName : "bg-line",
                        ].join(" ")}
                        style={{ height: point.value > 0 ? `max(${heightPercent}%, 2px)` : "2px" }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
            {/* X axis ticks */}
            <div className="mt-1.5 flex gap-px border-t border-line pt-1">
              {data.map((point, index) => (
                <div
                  key={point.key}
                  className="min-w-0 flex-1 text-center text-[9px] tabular-nums text-steel"
                >
                  {index % tickStep === 0 ? point.tick : ""}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex h-44 items-center justify-center rounded-2xl border border-dashed border-line bg-mist text-sm text-steel">
          Brak danych w wybranym okresie.
        </div>
      )}
    </div>
  );
}
