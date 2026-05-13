import { useState, useEffect, useRef, useCallback } from 'react'
import Editor from '@monaco-editor/react'
import { KeystrokeCapture } from './KeystrokeCapture'
import axios from './api'

const STUDENT_ID = 'student_live_' + Math.random().toString(36).slice(2, 8)
const PROBLEM_ID = 'stack_001'

const STAGE_JOURNAL = 'journal'
const STAGE_CODING = 'coding'
const STAGE_COMPREHENSION = 'comprehension'
const STAGE_DONE = 'done'

export default function StudentView() {
  const [stage, setStage] = useState(STAGE_JOURNAL)
  const [sessionId, setSessionId] = useState(null)
  const [problem, setProblem] = useState(null)
  const [journalText, setJournalText] = useState('')
  const [code, setCode] = useState('')
  const [testResults, setTestResults] = useState(null)
  const [runLoading, setRunLoading] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [submitReport, setSubmitReport] = useState(null)
  const [confidenceScore, setConfidenceScore] = useState(null)
  const [comprehensionAnswers, setComprehensionAnswers] = useState({})
  const [comprehensionTimer, setComprehensionTimer] = useState(600)
  const [selectedQuestions, setSelectedQuestions] = useState([])
  const [initError, setInitError] = useState(null)
  const editorContainerRef = useRef(null)
  const captureRef = useRef(null)
  const snapshotIntervalRef = useRef(null)

  // Create session and load problem on mount
  useEffect(() => {
    const init = async () => {
      const [sessionRes, problemRes] = await Promise.all([
        axios.post('/api/sessions', { student_id: STUDENT_ID, problem_id: PROBLEM_ID }),
        axios.get(`/api/problems/${PROBLEM_ID}`),
      ])
      setSessionId(sessionRes.data.id)
      setProblem(problemRes.data)
      setCode(problemRes.data.starter_code)
    }
    init().catch(err => {
      console.error(err)
      const detail = err.response
        ? `HTTP ${err.response.status}: ${JSON.stringify(err.response.data)}`
        : err.message
      setInitError(`Could not connect to backend (${detail}). Make sure uvicorn is running on port 8000.`)
    })
  }, [])

  // Keystroke capture setup
  const handleEditorMount = useCallback((editor) => {
    if (!sessionId) return
    const container = editor.getContainerDomNode()
    const capture = new KeystrokeCapture(sessionId, (score) => {
      setConfidenceScore(score)
    })
    capture.attach(container)
    captureRef.current = capture
  }, [sessionId])

  // Auto-snapshot every 60s
  useEffect(() => {
    if (stage !== STAGE_CODING || !sessionId) return
    snapshotIntervalRef.current = setInterval(() => {
      axios.post('/api/snapshot', { session_id: sessionId, code })
        .catch(() => {})
    }, 60000)
    return () => clearInterval(snapshotIntervalRef.current)
  }, [stage, sessionId, code])

  // Comprehension countdown
  useEffect(() => {
    if (stage !== STAGE_COMPREHENSION) return
    const t = setInterval(() => {
      setComprehensionTimer(s => {
        if (s <= 1) { clearInterval(t); handleSubmitComprehension(); return 0 }
        return s - 1
      })
    }, 1000)
    return () => clearInterval(t)
  }, [stage])

  const handleJournalSubmit = async () => {
    if (journalText.length < 100) return
    if (!sessionId) {
      setInitError('Session not ready — is the backend running?')
      return
    }
    try {
      await axios.post('/api/journal', { session_id: sessionId, text: journalText })
    } catch (_) {
      // Journal save failed but don't block the student
    }
    setStage(STAGE_CODING)
  }

  const handleRun = async () => {
    if (!sessionId) return
    setRunLoading(true)
    try {
      const res = await axios.post('/api/run', { session_id: sessionId, code })
      setTestResults(res.data.results)
    } finally {
      setRunLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!sessionId) return
    setSubmitLoading(true)
    try {
      const res = await axios.post('/api/submit', { session_id: sessionId, code })
      setSubmitReport(res.data)
      const qs = problem.comprehension_questions
      // Pick 2 random questions
      const indices = shuffleIndices(qs.length).slice(0, 2)
      setSelectedQuestions(indices.map(i => ({ index: i, text: qs[i] })))
      setStage(STAGE_COMPREHENSION)
    } finally {
      setSubmitLoading(false)
    }
  }

  const handleSubmitComprehension = async () => {
    if (!sessionId) return
    await axios.post('/api/comprehension', {
      session_id: sessionId,
      answers: comprehensionAnswers,
    }).catch(() => {})
    setStage(STAGE_DONE)
  }

  const confidenceBadgeColor = confidenceScore == null
    ? '#555'
    : confidenceScore >= 0.7 ? '#2e7d32'
    : confidenceScore >= 0.5 ? '#e65100'
    : '#b71c1c'

  const formatTimer = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  if (stage === STAGE_DONE) {
    return (
      <div style={styles.done}>
        <h2>Submission complete</h2>
        <p>Your work has been submitted. You may close this window.</p>
        {submitReport && (
          <div style={styles.scoreBox}>
            <h3>Scores</h3>
            <p>Correctness: {submitReport.scores?.correctness_score}%</p>
            <p>Complexity: {submitReport.scores?.complexity_score}%</p>
            <p>Quality: {submitReport.scores?.quality_score}%</p>
            <p>Robustness: {submitReport.scores?.robustness_score}%</p>
            <p><strong>Total: {submitReport.scores?.total_score}%</strong></p>
          </div>
        )}
        <p style={{ color: '#888', marginTop: 16 }}>
          <a href="/instructor" style={{ color: '#4fc3f7' }}>→ Instructor view</a>
        </p>
      </div>
    )
  }

  if (stage === STAGE_COMPREHENSION) {
    return (
      <div style={styles.comprehensionWrap}>
        <div style={styles.comprehensionHeader}>
          <span>Comprehension check</span>
          <span style={{ color: comprehensionTimer < 60 ? '#f04040' : '#ccc' }}>
            Time remaining: {formatTimer(comprehensionTimer)}
          </span>
        </div>
        <div style={styles.comprehensionBody}>
          {selectedQuestions.map(({ index, text }) => (
            <div key={index} style={{ marginBottom: 24 }}>
              <p style={{ fontWeight: 600, marginBottom: 8 }}>{text}</p>
              <textarea
                style={styles.comprehensionTextarea}
                rows={6}
                placeholder="Your answer..."
                value={comprehensionAnswers[index] || ''}
                onChange={e => setComprehensionAnswers(a => ({ ...a, [index]: e.target.value }))}
              />
            </div>
          ))}
          <button style={styles.btnPrimary} onClick={handleSubmitComprehension}>
            Submit answers
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>AUTHENTICATE</span>
        <span style={{ color: '#888', fontSize: 13 }}>{STUDENT_ID}</span>
        {stage === STAGE_CODING && confidenceScore != null && (
          <div style={{ ...styles.confidenceBadge, background: confidenceBadgeColor }}>
            Biometric: {confidenceScore.toFixed(2)}
          </div>
        )}
        {stage === STAGE_CODING && (
          <a href="/instructor" style={styles.headerLink}>Instructor view →</a>
        )}
      </div>

      {stage === STAGE_JOURNAL ? (
        <div style={styles.journalGate}>
          <div style={styles.journalPanel}>
            {problem && (
              <div style={styles.problemMini}>
                <h2 style={{ marginTop: 0 }}>{problem.title}</h2>
                <pre style={styles.description}>{problem.description}</pre>
              </div>
            )}
            <h3>Approach journal</h3>
            <p style={{ color: '#aaa', fontSize: 13 }}>
              Before you start coding, describe your approach. Minimum 100 characters.
            </p>
            <textarea
              style={styles.journalTextarea}
              rows={8}
              placeholder="Describe your planned approach..."
              value={journalText}
              onChange={e => setJournalText(e.target.value)}
            />
            {initError && (
              <div style={styles.errorBanner}>{initError}</div>
            )}
            <div style={styles.journalFooter}>
              <span style={{ color: journalText.length >= 100 ? '#4caf50' : '#888' }}>
                {journalText.length} / 100 characters
              </span>
              <button
                style={{ ...styles.btnPrimary, opacity: journalText.length < 100 ? 0.5 : 1 }}
                disabled={journalText.length < 100}
                onClick={handleJournalSubmit}
              >
                {sessionId ? 'Start coding' : 'Connecting…'}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div style={styles.columns}>
          {/* Left: problem + journal */}
          <div style={styles.leftPanel}>
            {problem && (
              <>
                <div style={styles.panelHeader}>Problem</div>
                <div style={styles.problemText}>
                  <strong style={{ fontSize: 15 }}>{problem.title}</strong>
                  <pre style={styles.description}>{problem.description}</pre>
                </div>
                <div style={styles.panelHeader}>Approach journal</div>
                <div style={styles.journalDisplay}>{journalText}</div>
              </>
            )}
          </div>

          {/* Centre: editor + results */}
          <div style={styles.centrePanel}>
            <div ref={editorContainerRef} style={styles.editorWrap}>
              <Editor
                height="100%"
                language="python"
                value={code}
                onChange={(v) => setCode(v || '')}
                theme="vs-dark"
                onMount={handleEditorMount}
                options={{
                  fontSize: 14,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                }}
              />
            </div>
            <div style={styles.editorActions}>
              <button style={styles.btnSecondary} onClick={handleRun} disabled={runLoading}>
                {runLoading ? 'Running…' : 'Run tests'}
              </button>
              <button style={styles.btnPrimary} onClick={handleSubmit} disabled={submitLoading}>
                {submitLoading ? 'Submitting…' : 'Submit'}
              </button>
            </div>
            {testResults && (
              <div style={styles.testResults}>
                {testResults.map(r => (
                  <div key={r.test_name} style={styles.testRow}>
                    <span style={{ color: r.passed ? '#4caf50' : '#f04040', marginRight: 8, fontSize: 16 }}>
                      {r.passed ? '✓' : '✗'}
                    </span>
                    <span style={{ fontFamily: 'monospace', fontSize: 13 }}>{r.test_name}</span>
                    {!r.passed && r.stderr && (
                      <span style={{ color: '#888', marginLeft: 8, fontSize: 12 }}>{r.stderr.slice(0, 80)}</span>
                    )}
                    {!r.passed && r.stdout && (
                      <span style={{ color: '#ccc', marginLeft: 8, fontSize: 12 }}>{r.stdout.slice(0, 80)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right: docs */}
          <div style={styles.rightPanel}>
            <div style={styles.panelHeader}>Documentation</div>
            <iframe
              src="https://docs.python.org/3/library/stdtypes.html#sequence-types-list-tuple-range"
              style={styles.docsIframe}
              sandbox="allow-same-origin allow-scripts"
              title="Python docs"
            />
          </div>
        </div>
      )}
    </div>
  )
}

function shuffleIndices(n) {
  const arr = Array.from({ length: n }, (_, i) => i)
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

const styles = {
  root: {
    display: 'flex', flexDirection: 'column', height: '100vh',
    background: '#0d1117', color: '#e6edf3', fontFamily: 'system-ui, sans-serif',
    overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 16, padding: '8px 20px',
    background: '#161b22', borderBottom: '1px solid #30363d', flexShrink: 0,
  },
  headerTitle: { fontWeight: 700, fontSize: 16, letterSpacing: 1 },
  headerLink: { marginLeft: 'auto', color: '#4fc3f7', fontSize: 13, textDecoration: 'none' },
  confidenceBadge: {
    marginLeft: 'auto', padding: '3px 10px', borderRadius: 12,
    fontSize: 12, fontWeight: 600, color: '#fff',
  },
  columns: {
    display: 'grid', gridTemplateColumns: '25% 50% 25%',
    flex: 1, overflow: 'hidden',
  },
  leftPanel: {
    borderRight: '1px solid #30363d', overflow: 'auto', padding: 16,
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  centrePanel: {
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    borderRight: '1px solid #30363d',
  },
  rightPanel: {
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  panelHeader: {
    fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase',
    color: '#8b949e', padding: '4px 0', borderBottom: '1px solid #30363d', marginBottom: 8,
  },
  problemText: { fontSize: 13, lineHeight: 1.6, overflowY: 'auto' },
  description: {
    whiteSpace: 'pre-wrap', fontFamily: 'system-ui, sans-serif',
    fontSize: 13, margin: '8px 0 0', color: '#cdd9e5',
  },
  journalDisplay: {
    fontSize: 12, color: '#8b949e', lineHeight: 1.6, fontStyle: 'italic',
    background: '#161b22', borderRadius: 6, padding: 10,
  },
  editorWrap: { flex: 1, overflow: 'hidden' },
  editorActions: {
    display: 'flex', gap: 8, padding: '8px 12px',
    background: '#161b22', borderTop: '1px solid #30363d', flexShrink: 0,
  },
  testResults: {
    borderTop: '1px solid #30363d', padding: '8px 12px',
    maxHeight: 160, overflowY: 'auto', background: '#0d1117', flexShrink: 0,
  },
  testRow: {
    display: 'flex', alignItems: 'center', padding: '2px 0',
  },
  docsIframe: {
    flex: 1, border: 'none', width: '100%', height: '100%', background: '#fff',
  },
  btnPrimary: {
    background: '#1f6feb', color: '#fff', border: 'none', borderRadius: 6,
    padding: '7px 18px', cursor: 'pointer', fontWeight: 600, fontSize: 13,
  },
  btnSecondary: {
    background: '#21262d', color: '#e6edf3', border: '1px solid #30363d',
    borderRadius: 6, padding: '7px 18px', cursor: 'pointer', fontSize: 13,
  },
  journalGate: {
    display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
    padding: 40, flex: 1, overflowY: 'auto',
  },
  journalPanel: {
    maxWidth: 680, width: '100%', background: '#161b22',
    borderRadius: 10, padding: 32, border: '1px solid #30363d',
  },
  journalTextarea: {
    width: '100%', boxSizing: 'border-box',
    background: '#0d1117', color: '#e6edf3', border: '1px solid #30363d',
    borderRadius: 6, padding: 12, fontSize: 14, fontFamily: 'system-ui, sans-serif',
    resize: 'vertical',
  },
  errorBanner: {
    background: '#3a0000', color: '#f04040', border: '1px solid #7a0000',
    borderRadius: 6, padding: '8px 12px', fontSize: 13, marginBottom: 8,
  },
  journalFooter: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12,
  },
  problemMini: {
    borderBottom: '1px solid #30363d', marginBottom: 20, paddingBottom: 20,
  },
  comprehensionWrap: {
    minHeight: '100vh', background: '#0d1117', color: '#e6edf3',
    fontFamily: 'system-ui, sans-serif',
  },
  comprehensionHeader: {
    display: 'flex', justifyContent: 'space-between', padding: '12px 32px',
    background: '#161b22', borderBottom: '1px solid #30363d',
    fontWeight: 700,
  },
  comprehensionBody: {
    maxWidth: 720, margin: '40px auto', padding: '0 24px',
  },
  comprehensionTextarea: {
    width: '100%', boxSizing: 'border-box',
    background: '#161b22', color: '#e6edf3', border: '1px solid #30363d',
    borderRadius: 6, padding: 12, fontSize: 14, fontFamily: 'system-ui, sans-serif',
    resize: 'vertical',
  },
  done: {
    minHeight: '100vh', display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    background: '#0d1117', color: '#e6edf3', fontFamily: 'system-ui, sans-serif',
  },
  scoreBox: {
    background: '#161b22', border: '1px solid #30363d',
    borderRadius: 8, padding: '20px 32px', marginTop: 16, minWidth: 280,
  },
}
