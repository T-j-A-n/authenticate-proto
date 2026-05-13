export default function ConfidenceCurve({ windows, snapshots, startedAt }) {
  const W = 800
  const H = 200
  const PAD = { top: 16, right: 16, bottom: 32, left: 48 }
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  if (!windows || windows.length === 0) {
    return <div style={{ color: '#888', padding: '16px', fontFamily: 'sans-serif' }}>No keystroke data yet.</div>
  }

  const maxElapsed = Math.max(...windows.map(w => w.elapsed_seconds || 0), 1)

  const toX = (elapsed) => PAD.left + ((elapsed || 0) / maxElapsed) * innerW
  const toY = (score) => PAD.top + (1 - score) * innerH

  const points = windows.map(w => `${toX(w.elapsed_seconds)},${toY(w.similarity_score)}`).join(' ')
  const areaPath = windows.length > 0
    ? `M${toX(windows[0].elapsed_seconds)},${toY(0.6)} ` +
      windows.map(w => `L${toX(w.elapsed_seconds)},${toY(w.similarity_score)}`).join(' ') +
      ` L${toX(windows[windows.length - 1].elapsed_seconds)},${toY(0.6)} Z`
    : ''

  // Large-diff snapshot markers
  const largeDiffSnaps = (snapshots || []).filter(s => s.diff_lines >= 20)

  // Y-axis ticks
  const yTicks = [0, 0.2, 0.4, 0.6, 0.8, 1.0]

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
      aria-label="Confidence curve"
    >
      {/* Background */}
      <rect x={PAD.left} y={PAD.top} width={innerW} height={innerH} fill="#1a1a2e" rx={4} />

      {/* Below-threshold shaded area */}
      <clipPath id="below-threshold">
        <rect x={PAD.left} y={toY(0.6)} width={innerW} height={innerH - (toY(0.6) - PAD.top)} />
      </clipPath>
      {areaPath && (
        <path d={areaPath} fill="rgba(255,160,0,0.18)" clipPath="url(#below-threshold)" />
      )}

      {/* Y-axis grid lines and labels */}
      {yTicks.map(v => (
        <g key={v}>
          <line
            x1={PAD.left} y1={toY(v)} x2={PAD.left + innerW} y2={toY(v)}
            stroke="#333" strokeWidth={0.5}
          />
          <text x={PAD.left - 6} y={toY(v) + 4} textAnchor="end" fill="#888" fontSize={10}>
            {v.toFixed(1)}
          </text>
        </g>
      ))}

      {/* Threshold line at 0.6 */}
      <line
        x1={PAD.left} y1={toY(0.6)} x2={PAD.left + innerW} y2={toY(0.6)}
        stroke="#ffa500" strokeWidth={1} strokeDasharray="6 4"
      />
      <text x={PAD.left + innerW - 2} y={toY(0.6) - 4} textAnchor="end" fill="#ffa500" fontSize={10}>
        threshold 0.6
      </text>

      {/* Large-diff vertical markers */}
      {largeDiffSnaps.map(s => (
        <line
          key={s.id}
          x1={toX(s.elapsed_seconds)} y1={PAD.top}
          x2={toX(s.elapsed_seconds)} y2={PAD.top + innerH}
          stroke="#f04040" strokeWidth={1} strokeDasharray="3 3" opacity={0.7}
        />
      ))}

      {/* Polyline */}
      {windows.length > 1 && (
        <polyline points={points} fill="none" stroke="#4fc3f7" strokeWidth={2} />
      )}

      {/* Data points */}
      {windows.map((w, i) => (
        <circle
          key={i}
          cx={toX(w.elapsed_seconds)}
          cy={toY(w.similarity_score)}
          r={3}
          fill={w.similarity_score >= 0.7 ? '#4caf50' : w.similarity_score >= 0.5 ? '#ffa500' : '#f04040'}
        />
      ))}

      {/* X-axis label */}
      <text x={PAD.left + innerW / 2} y={H - 4} textAnchor="middle" fill="#666" fontSize={11}>
        Elapsed time (seconds)
      </text>
    </svg>
  )
}
