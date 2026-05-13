import { useState, useEffect } from 'react'
import axios from './api'
import ConfidenceCurve from './ConfidenceCurve'

export default function InstructorView() {
  const [cohort, setCohort] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [compScore, setCompScore] = useState('')
  const [sortKey, setSortKey] = useState('anomaly_count')
  const [sortDir, setSortDir] = useState('desc')
  const [expandedSnap, setExpandedSnap] = useState(null)

  useEffect(() => {
    const load = () => axios.get('/api/instructor/cohort').then(r => setCohort(r.data))
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])

  const handleRowClick = async (sessionId) => {
    setSelectedId(sessionId)
    setTimeline(null)
    setTimelineLoading(true)
    setExpandedSnap(null)
    try {
      const res = await axios.get(`/api/instructor/session/${sessionId}/timeline`)
      setTimeline(res.data)
      setCompScore(res.data.session?.comprehension_score ?? '')
    } finally {
      setTimelineLoading(false)
    }
  }

  const handleSaveCompScore = async () => {
    if (!selectedId) return
    await axios.patch(`/api/instructor/session/${selectedId}/comprehension-score`, {
      score: parseFloat(compScore),
    })
    setCohort(c => c.map(s => s.session_id === selectedId ? { ...s, comprehension_score: parseFloat(compScore) } : s))
  }

  const sorted = [...cohort].sort((a, b) => {
    const av = a[sortKey] ?? -1
    const bv = b[sortKey] ?? -1
    return sortDir === 'asc' ? av - bv : bv - av
  })

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <span style={styles.title}>AUTHENTICATE — Instructor</span>
        <a href="/student" style={styles.headerLink}>← Student view</a>
      </div>

      <div style={styles.body}>
        {/* Cohort table */}
        <div style={styles.tableSection}>
          <table style={styles.table}>
            <thead>
              <tr>
                {[
                  ['student_id', 'Student'],
                  ['total_score', 'Score'],
                  ['anomaly_count', 'Anomaly windows'],
                  ['max_diff_lines', 'Max diff'],
                  ['comprehension_score', 'Comprehension'],
                ].map(([key, label]) => (
                  <th key={key} style={styles.th} onClick={() => handleSort(key)}>
                    {label} {sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                ))}
                <th style={styles.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(s => (
                <tr
                  key={s.session_id}
                  style={{
                    ...styles.tr,
                    background: s.flagged ? '#2a1d00' : s.session_id === selectedId ? '#1c2128' : 'transparent',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleRowClick(s.session_id)}
                >
                  <td style={styles.td}>{s.student_id}</td>
                  <td style={styles.td}>{s.total_score != null ? s.total_score + '%' : '—'}</td>
                  <td style={{ ...styles.td, color: s.anomaly_count >= 3 ? '#ffa500' : '#e6edf3' }}>
                    {s.anomaly_count}
                  </td>
                  <td style={{ ...styles.td, color: s.max_diff_lines >= 50 ? '#ffa500' : '#e6edf3' }}>
                    {s.max_diff_lines}
                  </td>
                  <td style={styles.td}>
                    {s.comprehension_score != null ? `${s.comprehension_score}/10` : '—'}
                  </td>
                  <td style={styles.td}>
                    {s.flagged
                      ? <span style={styles.flagBadge}>⚠ Review</span>
                      : <span style={styles.cleanBadge}>✓ Clean</span>
                    }
                  </td>
                </tr>
              ))}
              {cohort.length === 0 && (
                <tr><td colSpan={6} style={{ ...styles.td, color: '#888', textAlign: 'center', padding: 32 }}>
                  No sessions yet. Run seed.py or start a student session.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Session timeline */}
        {selectedId && (
          <div style={styles.timeline}>
            {timelineLoading && <div style={styles.loading}>Loading timeline…</div>}
            {timeline && (
              <>
                <div style={styles.sectionHeader}>
                  Confidence curve — {timeline.session.student_id}
                </div>
                <div style={{ padding: '12px 20px' }}>
                  <ConfidenceCurve
                    windows={timeline.keystroke_windows}
                    snapshots={timeline.snapshots}
                    startedAt={timeline.session.started_at}
                  />
                </div>

                <div style={styles.sectionHeader}>Commit log</div>
                <div style={styles.commitLog}>
                  {/* Journal entry */}
                  {timeline.approach_journal && (
                    <div style={styles.journalEntry}>
                      <div style={styles.commitMeta}>
                        <span style={styles.commitTag}>journal</span>
                        <span style={{ color: '#8b949e' }}>Approach journal</span>
                      </div>
                      <div style={styles.journalText}>{timeline.approach_journal}</div>
                    </div>
                  )}
                  {/* Snapshots */}
                  {timeline.snapshots.map((s, i) => {
                    const large = s.diff_lines >= 20
                    const prev = i > 0 ? timeline.snapshots[i - 1].code : ''
                    return (
                      <div
                        key={s.id}
                        style={{
                          ...styles.commitEntry,
                          borderLeft: large ? '3px solid #ffa500' : '3px solid #30363d',
                        }}
                      >
                        <div style={styles.commitMeta}>
                          <span style={{ color: '#8b949e', fontSize: 12 }}>
                            +{formatElapsed(s.elapsed_seconds)}
                          </span>
                          <span style={{
                            ...styles.diffBadge,
                            color: large ? '#ffa500' : '#8b949e',
                          }}>
                            +{s.diff_lines} lines
                          </span>
                          <span style={styles.commitTag}>{s.triggered_by}</span>
                          <button
                            style={styles.expandBtn}
                            onClick={() => setExpandedSnap(expandedSnap === s.id ? null : s.id)}
                          >
                            {expandedSnap === s.id ? 'Hide diff' : 'Show diff'}
                          </button>
                        </div>
                        {expandedSnap === s.id && (
                          <pre style={styles.diffPre}>
                            {renderDiff(prev, s.code)}
                          </pre>
                        )}
                      </div>
                    )
                  })}
                </div>

                <div style={styles.sectionHeader}>Comprehension answers</div>
                <div style={styles.comprehensionSection}>
                  {timeline.comprehension_answers ? (
                    Object.entries(timeline.comprehension_answers).map(([idx, answer]) => (
                      <div key={idx} style={{ marginBottom: 20 }}>
                        <div style={styles.questionText}>
                          Q{parseInt(idx) + 1}: {timeline.session.problem_id === 'stack_001' ? STACK_QUESTIONS[parseInt(idx)] : `Question ${parseInt(idx) + 1}`}
                        </div>
                        <div style={styles.answerText}>{answer}</div>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: '#888' }}>No comprehension answers submitted.</div>
                  )}
                  <div style={styles.scoreInput}>
                    <label style={{ fontSize: 13, marginRight: 8 }}>Comprehension score (0–10):</label>
                    <input
                      type="number" min={0} max={10} step={0.5}
                      value={compScore}
                      onChange={e => setCompScore(e.target.value)}
                      style={styles.scoreField}
                    />
                    <button style={styles.btnPrimary} onClick={handleSaveCompScore}>Save</button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const STACK_QUESTIONS = [
  "Explain why your push() and pop() methods have O(1) time complexity. What property of Python lists makes this possible?",
  "What would happen to your implementation if two threads called push() simultaneously? Describe the potential problem and how you would fix it.",
  "If you replaced your underlying data structure with a linked list, which operations would change in complexity and why?",
]

function formatElapsed(sec) {
  if (sec == null) return '?'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

function renderDiff(prev, current) {
  const prevLines = prev.split('\n')
  const currLines = current.split('\n')
  const result = []
  const maxLen = Math.max(prevLines.length, currLines.length)
  // Simple line-by-line diff display
  let pi = 0, ci = 0
  while (ci < currLines.length) {
    const line = currLines[ci]
    if (pi < prevLines.length && prevLines[pi] === line) {
      result.push({ type: 'same', text: '  ' + line })
      pi++
    } else {
      result.push({ type: 'add', text: '+ ' + line })
    }
    ci++
  }
  return result.map(({ type, text }) => (
    <span key={text + Math.random()} style={{ color: type === 'add' ? '#3fb950' : '#8b949e', display: 'block' }}>
      {text}
    </span>
  ))
}

const styles = {
  root: {
    minHeight: '100vh', background: '#0d1117', color: '#e6edf3',
    fontFamily: 'system-ui, sans-serif', display: 'flex', flexDirection: 'column',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 16, padding: '10px 24px',
    background: '#161b22', borderBottom: '1px solid #30363d',
  },
  title: { fontWeight: 700, fontSize: 16, letterSpacing: 1 },
  headerLink: { marginLeft: 'auto', color: '#4fc3f7', fontSize: 13, textDecoration: 'none' },
  body: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' },
  tableSection: { overflowX: 'auto', borderBottom: '1px solid #30363d' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    textAlign: 'left', padding: '10px 16px', background: '#161b22',
    color: '#8b949e', fontWeight: 600, borderBottom: '1px solid #30363d',
    cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
  },
  tr: { borderBottom: '1px solid #21262d', transition: 'background 0.1s' },
  td: { padding: '9px 16px', verticalAlign: 'middle' },
  flagBadge: {
    background: '#4a2e00', color: '#ffa500', border: '1px solid #7a4f00',
    borderRadius: 12, padding: '2px 10px', fontSize: 12, fontWeight: 600,
  },
  cleanBadge: {
    background: '#0d2a1a', color: '#3fb950', border: '1px solid #1a5c33',
    borderRadius: 12, padding: '2px 10px', fontSize: 12, fontWeight: 600,
  },
  timeline: {
    borderTop: '1px solid #30363d', flex: 1,
  },
  loading: { padding: 32, color: '#888', textAlign: 'center' },
  sectionHeader: {
    padding: '10px 20px', background: '#161b22',
    borderBottom: '1px solid #30363d', borderTop: '1px solid #30363d',
    fontWeight: 700, fontSize: 12, letterSpacing: 1,
    textTransform: 'uppercase', color: '#8b949e',
  },
  commitLog: { maxHeight: 320, overflowY: 'auto' },
  journalEntry: {
    padding: '10px 20px', borderBottom: '1px solid #21262d',
    borderLeft: '3px solid #1f6feb',
  },
  commitEntry: { padding: '8px 20px', borderBottom: '1px solid #21262d' },
  commitMeta: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  commitTag: {
    background: '#21262d', color: '#8b949e', borderRadius: 4,
    padding: '1px 6px', fontSize: 11,
  },
  diffBadge: { fontSize: 12, fontWeight: 600 },
  expandBtn: {
    background: 'none', color: '#4fc3f7', border: '1px solid #30363d',
    borderRadius: 4, padding: '1px 8px', fontSize: 11, cursor: 'pointer',
  },
  diffPre: {
    background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
    padding: 12, marginTop: 8, overflowX: 'auto', fontSize: 12, lineHeight: 1.5,
  },
  journalText: {
    fontSize: 13, color: '#cdd9e5', lineHeight: 1.6, marginTop: 4,
    fontStyle: 'italic',
  },
  comprehensionSection: { padding: '16px 20px' },
  questionText: {
    fontSize: 13, fontWeight: 600, color: '#8b949e', marginBottom: 6,
  },
  answerText: {
    fontSize: 13, color: '#cdd9e5', lineHeight: 1.7,
    background: '#161b22', borderRadius: 6, padding: '8px 12px',
  },
  scoreInput: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 },
  scoreField: {
    width: 70, background: '#161b22', color: '#e6edf3', border: '1px solid #30363d',
    borderRadius: 6, padding: '5px 8px', fontSize: 13,
  },
  btnPrimary: {
    background: '#1f6feb', color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 16px', cursor: 'pointer', fontWeight: 600, fontSize: 13,
  },
}
