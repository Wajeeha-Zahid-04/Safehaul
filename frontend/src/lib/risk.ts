import type { ExpressionSpecification } from 'maplibre-gl'
import type { RiskLevel } from '../api/types'

// Spec §4 Legend: Low green, Moderate yellow, High orange, Severe red, No Travel purple/black.
export const RISK_COLORS: Record<RiskLevel, string> = {
  0: '#16a34a',
  1: '#eab308',
  2: '#f97316',
  3: '#dc2626',
  4: '#581c87',
}

/** MapLibre expression mapping a feature's numeric `level` property to its risk colour. */
export const riskColorExpression: ExpressionSpecification = [
  'match',
  ['get', 'level'],
  1,
  RISK_COLORS[1],
  2,
  RISK_COLORS[2],
  3,
  RISK_COLORS[3],
  4,
  RISK_COLORS[4],
  RISK_COLORS[0],
]
