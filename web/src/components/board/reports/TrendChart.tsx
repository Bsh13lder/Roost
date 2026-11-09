import { formatCompact, formatMoney, monthShort } from "../money";
import type { TrendMonthOut } from "../../../api/money";

export interface TrendChartProps {
  months: readonly TrendMonthOut[];
}

// The drawing's numbers, in its own viewBox units.
const WIDTH = 300;
const HEIGHT = 120;
const BASE = 100; // the baseline's y
const PLOT = 86; // the tallest bar's height
const PAD = 10;
const MAX_BAR = 14;
const GAP = 3;
const MAX_SERIES = 3; // the palette has three series colours

// A series' tallest value: a scale for its bars, never a sum (each currency is drawn on its own scale).
const peak = (months: readonly TrendMonthOut[], code: string) =>
  Math.max(0, ...months.map((month) => Number(month.totals[code] ?? 0)));

// Spent per month, one series per currency, in plain SVG (Task 15; its own lazy chunk). Each currency has its own
// scale and its own legend entry, and nothing is added across currencies. A hidden table carries the same numbers.
export function TrendChart({ months }: TrendChartProps) {
  const codes = [...new Set(months.flatMap((month) => Object.keys(month.totals)))].sort().slice(0, MAX_SERIES);
  const peaks = new Map(codes.map((code) => [code, peak(months, code)]));
  if (codes.every((code) => (peaks.get(code) ?? 0) <= 0)) return <p className="chart__none">Nothing spent in these months.</p>;
  const slot = (WIDTH - 2 * PAD) / Math.max(months.length, 1);
  const bar = Math.min(MAX_BAR, (slot - GAP) / codes.length - GAP);
  const groupWidth = codes.length * bar + (codes.length - 1) * GAP;
  return (
    <div className="chart-wrap">
      <svg className="chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Spent per month, one series per currency">
        <line className="chart__base" x1={PAD / 2} x2={WIDTH - PAD / 2} y1={BASE} y2={BASE} />
        {months.map((month, index) => {
          const left = PAD + index * slot + (slot - groupWidth) / 2;
          const now = index === months.length - 1;
          return (
            <g key={month.month} className="chart__month">
              {codes.flatMap((code, series) => {
                const value = Number(month.totals[code] ?? 0);
                const scale = peaks.get(code) ?? 0;
                if (month.totals[code] === undefined || scale <= 0) return [];
                const height = Math.round((value / scale) * PLOT);
                return [(
                  <rect key={code} className={`chart__bar chart__bar--${series}${now ? " is-now" : ""}`}
                    x={left + series * (bar + GAP)} y={BASE - height} width={bar} height={height} rx={2}>
                    <title>{monthShort(month.month)}: {formatMoney(month.totals[code], code)}</title>
                  </rect>
                )];
              })}
              <text x={left + groupWidth / 2} y={HEIGHT - 6} textAnchor="middle">{monthShort(month.month)}</text>
            </g>
          );
        })}
      </svg>
      <ul className="legend" aria-label="Currencies">
        {codes.map((code, series) => (
          <li key={code}><i className={`chart-key chart-key--${series}`} aria-hidden="true" />
            {code} (scale {formatCompact(peaks.get(code) ?? 0, code)})</li>
        ))}
      </ul>
      <table className="sr-only">
        <caption>Spent per month</caption>
        <thead><tr><th scope="col">Month</th>{codes.map((code) => <th key={code} scope="col">{code}</th>)}</tr></thead>
        <tbody>
          {months.map((month) => (
            <tr key={month.month}>
              <th scope="row">{monthShort(month.month)} {month.month.slice(0, 4)}</th>
              {codes.map((code) => (
                <td key={code}>{month.totals[code] === undefined ? "—" : formatMoney(month.totals[code], code)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default TrendChart;
