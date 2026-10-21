import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/risk'

interface Props {
  heatmapAvailable: boolean
  heatmapOn: boolean
  onToggleHeatmap: () => void
}

export function Legend({ heatmapAvailable, heatmapOn, onToggleHeatmap }: Props) {
  return (
    <div className="absolute top-3 right-14 left-3 rounded-lg bg-white/95 px-3 py-2 shadow-md ring-1 ring-slate-200 md:right-auto">
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-700 md:flex-col">
        {RISK_LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: RISK_COLORS[level] }}
            />
            {RISK_LABELS[level]}
          </li>
        ))}
      </ul>
      <label
        className={`mt-2 flex items-center gap-2 border-t border-slate-200 pt-2 text-xs font-medium ${
          heatmapAvailable ? 'cursor-pointer text-slate-800' : 'cursor-not-allowed text-slate-400'
        }`}
      >
        <input
          type="checkbox"
          role="switch"
          checked={heatmapOn}
          disabled={!heatmapAvailable}
          onChange={onToggleHeatmap}
          className="accent-sky-600"
        />
        Weather heatmap
      </label>
    </div>
  )
}
