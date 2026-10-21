import { Popup } from 'react-map-gl/maplibre'
import type { CheckpointResult } from '../api/types'
import { formatEta } from '../lib/format'
import { RISK_COLORS } from '../lib/risk'

interface Props {
  checkpoint: CheckpointResult
  onClose: () => void
}

export function CheckpointPopup({ checkpoint: cp, onClose }: Props) {
  return (
    <Popup
      longitude={cp.lon}
      latitude={cp.lat}
      anchor="bottom"
      offset={10}
      closeOnClick={false}
      onClose={onClose}
      maxWidth="280px"
    >
      <div className="space-y-1.5 text-xs text-slate-700">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ backgroundColor: RISK_COLORS[cp.level] }}
          />
          <span className="text-sm font-semibold text-slate-900">{cp.level_label}</span>
          <span className="text-slate-500">· mile {cp.distance_mi}</span>
        </div>
        <div>
          <span className="font-medium">ETA</span> {formatEta(cp.eta)}{' '}
          <span className="text-slate-500">(forecast for {formatEta(cp.forecast_hour)})</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-2">
          <dt className="font-medium">Wind</dt>
          <dd>
            {cp.wind_mph} mph <span className="text-slate-500">(gusts {cp.gust_mph}, not scored)</span>
          </dd>
          <dt className="font-medium">Rain</dt>
          <dd>{cp.rain_in} in/hr</dd>
          <dt className="font-medium">Snow</dt>
          <dd>{cp.snow_in} in/hr</dd>
          <dt className="font-medium">Precip</dt>
          <dd>{cp.precip_in} in/hr</dd>
        </dl>
        <ul className="border-t border-slate-200 pt-1.5">
          {cp.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
    </Popup>
  )
}
