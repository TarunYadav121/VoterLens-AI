import { Component, useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, Bot, Check, ChevronDown, ClipboardCheck,
  CornerDownRight, Database, Download, ExternalLink, FileDiff, FileSpreadsheet,
  FlaskConical, FolderOpen, Globe, Languages, LayoutDashboard, Menu, MessageSquare,
  RefreshCw, RotateCcw, Search, Send, ShieldCheck, SlidersHorizontal, Sparkles,
  Upload, User, X, XCircle,
} from 'lucide-react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  analyzeFiles, chatExplain, chatMessage, compareAreas, downloadExport,
  downloadSample, explainQuestion, getHealth, getRecord, getSampleMetadata,
  recheckFinding, runChallenge,
} from './api/client'
import {
  ASSISTANT_ACTIONS, parseAssistantCommand, serializeCsv, parseCsv,
  validateAssistantAction, highestFinding, applyDraftChange,
} from './assistant/actions'
import {
  findingMetric, formatNumber, formatPercent, formatTimestamp, reconcileCounts,
  recordLists,
} from './utils/audit'
import './App.css'

const NAV_ITEMS = [
  ['ingestion', 'Ingestion & Upload', Upload],
  ['overview', 'Executive Overview', LayoutDashboard],
  ['findings', 'Findings & Evidence', ShieldCheck],
  ['areas', 'Area Analytics', BarChart3],
  ['records', 'Record Diff Inspector', FileDiff],
  ['counterfactual', 'Counterfactual Audit Lab', SlidersHorizontal],
  ['assistant', 'Multilingual Assistant', Languages],
  ['benchmark', 'False-Alarm Benchmark', FlaskConical],
  ['reports', 'Reports & Exports', FileSpreadsheet],
]

const EMPTY_WORKSPACE = { previousFile: null, currentFile: null, analysis: null, selectedFinding: null, counterfactual: null }

function App() {
  const [page, setPage] = useState('ingestion')
  const [workspace, setWorkspace] = useState(EMPTY_WORKSPACE)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState({ state: 'connecting', version: null, checkedAt: null })
  const [notice, setNotice] = useState(null)
  const [loading, setLoading] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [draftHistory, setDraftHistory] = useState([])

  const checkHealth = useCallback(async (signal) => {
    try {
      const result = await getHealth(signal)
      setHealth({ state: result.status === 'ok' ? 'connected' : 'disconnected', version: result.version, checkedAt: new Date().toISOString() })
    } catch (error) {
      if (error.name !== 'AbortError') setHealth({ state: 'disconnected', version: null, checkedAt: new Date().toISOString() })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    window.queueMicrotask(() => checkHealth(controller.signal))
    const timer = window.setInterval(() => checkHealth(), 25000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [checkHealth])

  const setError = (error) => setNotice({ kind: 'error', text: error.message || 'Something went wrong.' })
  const navigate = (nextPage) => { setPage(nextPage); setSidebarOpen(false) }

  async function submitAnalysis(previousFile, currentFile) {
    setLoading(true)
    setNotice(null)
    try {
      const analysis = await analyzeFiles(previousFile, currentFile)
      setWorkspace({ ...EMPTY_WORKSPACE, previousFile, currentFile, analysis })
      navigate('overview')
      setNotice({ kind: 'success', text: `Analysis ${analysis.analysis_id} completed.` })
    } catch (error) {
      setWorkspace((current) => ({ ...current, analysis: null, selectedFinding: null }))
      setError(error)
    } finally {
      setLoading(false)
    }
  }

  async function loadSample() {
    setLoading(true)
    setNotice(null)
    try {
      await getSampleMetadata()
      const [previousBlob, currentBlob] = await Promise.all([downloadSample('previous'), downloadSample('current')])
      await submitAnalysis(new File([previousBlob], 'previous_roll.csv', { type: 'text/csv' }), new File([currentBlob], 'current_roll.csv', { type: 'text/csv' }))
    } catch (error) {
      setError(error)
      setLoading(false)
    }
  }

  async function applyDraftEdit(edit) {
    if (!workspace.previousFile || !workspace.currentFile) throw new Error('The original uploaded files are no longer available in this browser session.')
    const beforeFile = workspace.currentFile
    const rows = parseCsv(await beforeFile.text())
    const changed = applyDraftChange(rows, edit)
    const nextFile = new File([serializeCsv(changed.rows)], beforeFile.name, { type: 'text/csv' })
    setLoading(true)
    try {
      const nextAnalysis = await analyzeFiles(workspace.previousFile, nextFile)
      setDraftHistory((history) => [...history, { ...edit, previousValue: changed.previousValue, nextValue: changed.nextValue, beforeFile }])
      setWorkspace((current) => ({ ...current, currentFile: nextFile, analysis: nextAnalysis, selectedFinding: null }))
      setNotice({ kind: 'success', text: 'Draft revision applied and re-analyzed. Original files remain unchanged.' })
      return nextAnalysis
    } catch (error) {
      setWorkspace((current) => ({ ...current, analysis: null, selectedFinding: null }))
      setNotice({ kind: 'error', text: `Draft analysis failed: ${error.message}. The draft file is retained, but no analysis is current.` })
      throw error
    } finally { setLoading(false) }
  }

  async function undoDraftEdit() {
    const last = draftHistory.at(-1)
    if (!last || !workspace.previousFile) throw new Error('There is no confirmed draft change to undo.')
    setLoading(true)
    try {
      const restoredAnalysis = await analyzeFiles(workspace.previousFile, last.beforeFile)
      setDraftHistory((history) => history.slice(0, -1))
      setWorkspace((current) => ({ ...current, currentFile: last.beforeFile, analysis: restoredAnalysis, selectedFinding: null }))
      setNotice({ kind: 'success', text: 'The latest draft change was undone and the prior draft was re-analyzed.' })
      return restoredAnalysis
    } finally { setLoading(false) }
  }

  function downloadDraftCsv() {
    if (!workspace.currentFile || draftHistory.length === 0) throw new Error('Confirm a draft change before downloading the revised synthetic CSV.')
    const url = URL.createObjectURL(workspace.currentFile)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'voterlens-revised-synthetic-current.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  function resetWorkspace() {
    setWorkspace(EMPTY_WORKSPACE)
    setNotice({ kind: 'success', text: 'Client workspace cleared. The backend has no session-reset endpoint, so server memory was not erased.' })
    setResetOpen(false)
    navigate('ingestion')
  }

  const currentLabel = NAV_ITEMS.find(([key]) => key === page)?.[1] || 'Audit workspace'
  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Activity size={20} /></div>
          <div><strong>VoterLens AI</strong><span>Explainable roll audit</span></div>
        </div>
        <div className="synthetic-badge"><ShieldCheck size={15} /> Synthetic data only</div>
        <nav aria-label="Primary navigation">
          {NAV_ITEMS.map(([key, label, Icon]) => (
            <button key={key} className={page === key ? 'nav-item active' : 'nav-item'} onClick={() => navigate(key)}>
              <Icon size={17} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <BackendStatus health={health} onRetry={() => checkHealth()} />
          <button className="reset-link" onClick={() => setResetOpen(true)}><RotateCcw size={15} /> Reset audit</button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="menu-button" aria-label="Open navigation" onClick={() => setSidebarOpen(!sidebarOpen)}><Menu size={21} /></button>
          <div><span className="eyebrow">AUDIT WORKSPACE</span><h1>{currentLabel}</h1></div>
          <div className="topbar-meta"><span className="analysis-chip">{workspace.analysis?.analysis_id || 'No active analysis'}</span><BackendStatus health={health} compact /></div>
        </header>
        <div className="content">
          <div className="privacy-banner"><AlertTriangle size={17} /><span><strong>Synthetic data only.</strong> Do not upload real voter information. Findings are signals for human review, not proof of wrongdoing.</span></div>
          {notice && <div className={`notice ${notice.kind}`} role="status">{notice.kind === 'error' ? <XCircle size={17} /> : <Check size={17} />}<span>{notice.text}</span><button aria-label="Dismiss" onClick={() => setNotice(null)}><X size={15} /></button></div>}
          {page === 'ingestion' && <Ingestion workspace={workspace} onSubmit={submitAnalysis} onSample={loadSample} loading={loading} />}
          {page === 'overview' && <Overview analysis={workspace.analysis} onNavigate={navigate} onFinding={(finding) => { setWorkspace((s) => ({ ...s, selectedFinding: finding })); navigate('findings') }} />}
          {page === 'findings' && <Findings analysis={workspace.analysis} selectedFinding={workspace.selectedFinding} onSelect={(finding) => setWorkspace((s) => ({ ...s, selectedFinding: finding }))} />}
          {page === 'areas' && <Areas analysis={workspace.analysis} />}
          {page === 'records' && <Records analysis={workspace.analysis} onError={setError} />}
          {page === 'counterfactual' && <Counterfactual analysis={workspace.analysis} saved={workspace.counterfactual} onSave={(value) => setWorkspace((s) => ({ ...s, counterfactual: value }))} onError={setError} />}
          {page === 'assistant' && <Assistant analysis={workspace.analysis} selectedFinding={workspace.selectedFinding} onError={setError} onOpenChat={() => setChatOpen(true)} />}
          {page === 'benchmark' && <Benchmark onError={setError} />}
          {page === 'reports' && <Reports analysis={workspace.analysis} onError={setError} />}
        </div>
      </main>
      <ErrorBoundary>
        <InsightAssistantChat
          analysis={workspace.analysis}
          isOpen={chatOpen}
          onToggle={() => setChatOpen((v) => !v)}
          onNavigate={navigate}
          onLoadSample={loadSample}
          isAppLoading={loading}
          selectedFinding={workspace.selectedFinding}
          page={page}
          onSelectFinding={(finding) => { setWorkspace((current) => ({ ...current, selectedFinding: finding })); navigate('findings') }}
          onApplyDraftEdit={applyDraftEdit}
          onUndoDraftEdit={undoDraftEdit}
          onDownloadDraft={downloadDraftCsv}
          draftHistory={draftHistory}
        />
      </ErrorBoundary>
      {resetOpen && <ConfirmDialog onCancel={() => setResetOpen(false)} onConfirm={resetWorkspace} />}
    </div>
  )
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '16px', margin: '16px', background: '#fee2e2', border: '1px solid #f87171', borderRadius: '8px', color: '#991b1b', zIndex: 1000, position: 'relative' }}>
          <h4 style={{ margin: '0 0 6px', fontSize: '14px' }}>Component Error</h4>
          <p style={{ margin: '0 0 10px', fontSize: '12px' }}>{this.state.error?.message || 'An unexpected rendering error occurred.'}</p>
          <button
            className="button secondary sm"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function ConfirmDialog({ onCancel, onConfirm }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Reset Workspace</h2>
        <p>Are you sure you want to clear the current analysis and files? This will reset all loaded data.</p>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button className="button secondary sm" onClick={onCancel}>Cancel</button>
          <button className="button danger sm" onClick={onConfirm}>Reset</button>
        </div>
      </div>
    </div>
  )
}

function BackendStatus({ health, compact = false, onRetry }) {
  return (
    <div className={compact ? 'backend-status compact' : 'backend-status'}>
      <span className={`status-dot ${health.state}`} />
      <span>{health.state === 'connected' ? `Connected · ${health.version || 'unknown version'}` : health.state === 'connecting' ? 'Connecting…' : 'Backend disconnected'}</span>
      {!compact && health.checkedAt && <small>Checked {formatTimestamp(health.checkedAt)}</small>}
      {!compact && health.state === 'disconnected' && <button className="text-button" onClick={onRetry}>Retry</button>}
    </div>
  )
}

function Ingestion({ workspace, onSubmit, onSample, loading }) {
  const [previous, setPrevious] = useState(workspace.previousFile)
  const [current, setCurrent] = useState(workspace.currentFile)
  const [dragging, setDragging] = useState(null)
  const choose = (setter) => (event) => setter(event.target.files?.[0] || null)
  const drop = (setter) => (event) => { event.preventDefault(); setDragging(null); const file = event.dataTransfer.files?.[0]; if (file) setter(file) }
  const valid = (file) => !file || file.name.toLowerCase().endsWith('.csv')
  const canAnalyze = previous && current && valid(previous) && valid(current)
  return (
    <section className="page-section">
      <div className="hero-copy"><span className="eyebrow">START AN AUDIT</span><h2>Compare two fictional electoral rolls.</h2><p>Upload a previous and current CSV to classify record changes, validate quality, and surface area-level signals with reproducible evidence.</p></div>
      <div className="upload-grid">
        <UploadCard label="Previous roll" hint="Baseline CSV" file={previous} dragging={dragging === 'previous'} setDragging={setDragging} onDrop={drop(setPrevious)} onChange={choose(setPrevious)} />
        <UploadCard label="Current roll" hint="Updated CSV" file={current} dragging={dragging === 'current'} setDragging={setDragging} onDrop={drop(setCurrent)} onChange={choose(setCurrent)} />
      </div>
      {(!valid(previous) || !valid(current)) && <div className="inline-error"><AlertTriangle size={16} /> Only files with a .csv extension can be uploaded.</div>}
      <div className="action-row"><button className="button primary" disabled={!canAnalyze || loading} onClick={() => onSubmit(previous, current)}>{loading ? <><RefreshCw className="spin" size={17} /> Analyzing…</> : <><Upload size={17} /> Analyze files</>}</button><button className="button secondary" disabled={loading} onClick={onSample}><Database size={17} /> Load supplied sample</button></div>
      <div className="info-grid">
        <InfoTile icon={<ClipboardCheck size={18} />} title="Reproducible checks" text="Every finding keeps its rule, evidence, baseline, limitations, and next step." />
        <InfoTile icon={<ShieldCheck size={18} />} title="Responsible by design" text="An anomaly is a review signal. It does not establish fraud, intent, or wrongdoing." />
        <InfoTile icon={<Database size={18} />} title="In-memory session" text="Uploaded data stays in the active backend analysis session and is not saved by this browser." />
      </div>
    </section>
  )
}

function UploadCard({ label, hint, file, dragging, setDragging, onDrop, onChange }) {
  return <div className={`upload-card ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(label.startsWith('Previous') ? 'previous' : 'current') }} onDragLeave={() => setDragging(null)} onDrop={onDrop}>
    <div className="upload-icon"><FileSpreadsheet size={22} /></div><div><h3>{label}</h3><span>{hint} · CSV only</span></div>
    {file ? <div className="file-selected"><Check size={15} /><span>{file.name}<small>{(file.size / 1024).toFixed(1)} KB</small></span><button aria-label={`Remove ${label}`} onClick={() => onChange({ target: { files: [] } })}><X size={15} /></button></div> : <label className="file-picker"><FolderOpen size={16} /> Choose file<input type="file" accept=".csv,text/csv" onChange={onChange} /></label>}
  </div>
}

function Overview({ analysis, onNavigate, onFinding }) {
  if (!analysis) return <EmptyState title="No active analysis" text="Upload two CSV files to populate the executive overview." action="Go to ingestion" onAction={() => onNavigate('ingestion')} />
  const summary = analysis.summary || {}
  const net = Number(summary.current_records || 0) - Number(summary.previous_records || 0)
  const reconciliation = reconcileCounts(summary)
  const chartData = [['Added', summary.added, 'blue'], ['Deleted', summary.deleted, 'rose'], ['Modified', summary.modified, 'amber'], ['Unchanged', summary.unchanged, 'green']].map(([name, value, color]) => ({ name, value: Number(value || 0), color }))
  return <section className="page-section">
    <PageIntro eyebrow="EXECUTIVE OVERVIEW" title="What changed between rolls?" text="A factual summary of records classified by the comparison engine. Counts are outcomes of this run, not verified voter identities." />
    <div className="metric-grid">{[['Previous records', summary.previous_records, 'navy'], ['Current records', summary.current_records, 'navy'], ['Net roll change', net, net >= 0 ? 'blue' : 'rose'], ['Added records', summary.added, 'blue'], ['Deleted records', summary.deleted, 'rose'], ['Modified records', summary.modified, 'amber']].map(([label, value, tone]) => <MetricCard key={label} label={label} value={value} tone={tone} />)}</div>
    <div className="split-grid"><Panel title="Change distribution"><div className="chart-wrap"><ResponsiveContainer width="100%" height={260}><BarChart data={chartData} margin={{ top: 10, right: 15, left: -20, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="value" radius={[4, 4, 0, 0]}>{chartData.map((item) => <Cell key={item.name} fill={`var(--${item.color})`} />)}</Bar></BarChart></ResponsiveContainer></div></Panel><Panel title="Secondary outcomes"><div className="secondary-list"><DataLine label="Unchanged records" value={summary.unchanged} /><DataLine label="Ambiguous previous" value={summary.ambiguous_previous} /><DataLine label="Ambiguous current" value={summary.ambiguous_current} /></div></Panel></div>
    <Panel title="Count reconciliation" className={reconciliation.passed ? 'reconciliation pass' : 'reconciliation fail'}><div className="reconcile-head"><div className="reconcile-status">{reconciliation.passed ? <Check size={17} /> : <AlertTriangle size={17} />}<strong>{reconciliation.passed ? 'Count reconciliation passed.' : 'Count reconciliation failed — review required.'}</strong></div><span className="pill">{reconciliation.passed ? 'Both equations balance' : 'Mismatch detected'}</span></div><div className="equations"><code>Previous: {reconciliation.previousLeft} = {summary.deleted || 0} deleted + {summary.modified || 0} modified + {summary.unchanged || 0} unchanged + {summary.ambiguous_previous || 0} ambiguous</code><code>Current: {reconciliation.currentLeft} = {summary.added || 0} added + {summary.modified || 0} modified + {summary.unchanged || 0} unchanged + {summary.ambiguous_current || 0} ambiguous</code></div>{analysis.validation_warnings?.count_consistency?.length > 0 && <div className="inline-error"><AlertTriangle size={15} /> Backend consistency warnings: {analysis.validation_warnings.count_consistency.join(' ')}</div>}</Panel>
    <Panel title="Findings preview"><FindingsTable findings={(analysis.findings || []).slice(0, 5)} onSelect={onFinding} /><button className="button text-button" onClick={() => onNavigate('findings')}>View all findings <ChevronDown size={15} /></button></Panel>
  </section>
}

function Findings({ analysis, selectedFinding, onSelect }) {
  const [priority, setPriority] = useState('all')
  const [category, setCategory] = useState('all')
  const [recheck, setRecheck] = useState(null)
  if (!analysis) return <EmptyState title="No findings yet" text="Run an analysis to inspect evidence passports." />
  const findings = (analysis.findings || []).filter((finding) => (priority === 'all' || finding.review_priority === priority) && (category === 'all' || finding.category === category))
  async function doRecheck(finding) {
    try { setRecheck({ id: finding.finding_id, loading: true }); const result = await recheckFinding({ analysis_id: analysis.analysis_id, finding_id: finding.finding_id }); setRecheck({ id: finding.finding_id, result }) } catch (error) { setRecheck({ id: finding.finding_id, error: error.message }) }
  }
  const passport = selectedFinding || findings[0]
  return <section className="page-section"><PageIntro eyebrow="FINDINGS & EVIDENCE PASSPORTS" title="Signals that warrant human review" text="Findings are rule-based observations. Possible explanations are not verified causes." /><div className="filter-bar"><FilterSelect label="Priority" value={priority} onChange={setPriority} options={['all', 'HIGH', 'MEDIUM', 'LOW']} /><FilterSelect label="Category" value={category} onChange={setCategory} options={['all', 'DATA_QUALITY', 'AGGREGATE_PATTERN']} /><span className="result-count">{findings.length} finding{findings.length === 1 ? '' : 's'}</span></div><div className="findings-layout"><div className="finding-list">{findings.map((finding) => <FindingCard key={finding.finding_id} finding={finding} selected={passport?.finding_id === finding.finding_id} onSelect={() => onSelect(finding)} onRecheck={() => doRecheck(finding)} recheck={recheck?.id === finding.finding_id ? recheck : null} />)}{!findings.length && <EmptyState title="No findings match these filters" text="Reset the filters to inspect all API-returned findings." />}</div>{passport && <EvidencePassport finding={passport} passport={analysis.evidence_passports?.find((item) => item.finding_id === passport.finding_id)} analysis={analysis} recheck={recheck?.id === passport.finding_id ? recheck : null} />}</div></section>
}

function FindingCard({ finding, selected, onSelect, onRecheck, recheck }) {
  return <div className={`finding-card ${selected ? 'selected' : ''}`} role="button" tabIndex={0} onClick={onSelect} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect() } }}><div className="finding-card-top"><span className={`priority ${finding.review_priority?.toLowerCase()}`}>{finding.review_priority} review</span><span className="category-label">{finding.category === 'DATA_QUALITY' ? 'Data quality' : 'Area pattern'}</span></div><h3>{finding.title}</h3><p>{finding.description}</p><div className="finding-meta"><span>{finding.finding_id}</span><span>{finding.affected_record_count} record{finding.affected_record_count === 1 ? '' : 's'}</span>{finding.affected_area_id && <span>{finding.affected_area_id}</span>}</div><div className="finding-actions"><span>Open Evidence Passport →</span><button type="button" className="mini-button" onClick={(event) => { event.stopPropagation(); onRecheck() }} disabled={recheck?.loading}>{recheck?.loading ? 'Checking…' : 'Recheck'}</button>{recheck?.result && <span className={recheck.result.match ? 'recheck-pass' : 'recheck-fail'}>{recheck.result.match ? 'Match' : 'Mismatch'}</span>}</div>{recheck?.error && <span className="inline-error">{recheck.error}</span>}</div>
}

function EvidencePassport({ finding, passport, analysis, recheck }) {
  const evidence = finding.supporting_evidence || {}
  return <aside className="passport panel"><div className="passport-heading"><div><span className="eyebrow">EVIDENCE PASSPORT</span><h2>{finding.title}</h2></div><span className="rule-chip">{finding.rule_id}</span></div><NoticeText text="This finding is a statistical signal for human audit, NOT proof of wrongdoing." /><InfoRow label="Observation" value={passport?.observation || finding.description} /><InfoRow label="Supporting evidence" value={JSON.stringify(evidence, null, 2)} code /><InfoRow label="Baseline methodology" value={`${finding.baseline_method || passport?.baseline_method || 'Not supplied'} · comparison group ${finding.comparison_group_size ?? passport?.comparison_group_size ?? 'not available'}`} /><InfoRow label="Threshold" value={finding.threshold == null ? 'Not supplied' : `${finding.threshold} (backend units)`} /><InfoRow label="Limitations" value={finding.limitations || passport?.limitations || 'Not supplied'} /><ListBlock title="Possible alternative explanations" items={finding.possible_explanations || passport?.possible_alternative_explanations || []} /><ListBlock title="Recommended next step" items={finding.recommended_next_step ? [finding.recommended_next_step] : passport?.recommended_next_steps || []} /><div className="passport-footer"><span>Analysis {analysis.analysis_id}</span><span>Fingerprints stored with run</span></div>{recheck?.result && <div className="recheck-box"><strong>Recheck {recheck.result.match ? 'matched' : 'did not match'}</strong><small>{formatTimestamp(recheck.result.recheck_timestamp)}</small></div>}</aside>
}

function Areas({ analysis }) {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('area_id')
  if (!analysis) return <EmptyState title="No area data" text="Run an analysis to inspect area-level rates." />
  const areas = (analysis.area_comparison || []).filter((area) => `${area.area_id} ${area.area_name}`.toLowerCase().includes(search.toLowerCase())).sort((a, b) => String(a[sort] ?? '').localeCompare(String(b[sort] ?? ''), undefined, { numeric: true }))
  const chart = areas.slice(0, 20)
  return <section className="page-section"><PageIntro eyebrow="AREA ANALYTICS" title="Rates with denominators visible" text="Removal rate = deleted / previous count. Addition rate = added / current count. Baselines and flags come from the backend." /><div className="toolbar"><label className="search-field"><Search size={16} /><input placeholder="Search area ID or name" value={search} onChange={(event) => setSearch(event.target.value)} /></label><FilterSelect label="Sort" value={sort} onChange={setSort} options={['area_id', 'previous_count', 'removal_rate_pct', 'addition_rate_pct']} /></div><Panel title="Per-area removal rates"><div className="chart-wrap"><ResponsiveContainer width="100%" height={280}><AreaChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="area_id" tick={{ fontSize: 11 }} /><YAxis unit="%" tick={{ fontSize: 12 }} /><Tooltip formatter={(value) => formatPercent(value)} /><Area type="monotone" dataKey="removal_rate_pct" stroke="var(--blue)" fill="var(--blue-soft)" connectNulls /></AreaChart></ResponsiveContainer></div></Panel><Panel title={`${areas.length} areas`}><div className="table-scroll"><table><thead><tr>{['Area', 'Type', 'Previous', 'Current', 'Net', 'Added', 'Deleted', 'Removal rate', 'Addition rate', 'Baseline', 'Flag'].map((head) => <th key={head}>{head}</th>)}</tr></thead><tbody>{areas.map((area) => <tr key={area.area_id}><td><strong>{area.area_id}</strong><small>{area.area_name}</small></td><td>{area.area_type || '—'}</td><td>{formatNumber(area.previous_count)}</td><td>{formatNumber(area.current_count)}</td><td>{formatNumber(area.net_change)}</td><td>{formatNumber(area.added_count)}</td><td>{formatNumber(area.deleted_count)}</td><td>{formatPercent(area.removal_rate_pct)}</td><td>{formatPercent(area.addition_rate_pct)}</td><td>{formatPercent(area.baseline_removal_rate_pct)}</td><td>{area.flagged_removal || area.flagged_addition ? <span className="priority high">Review</span> : <span className="status-text">Normal range</span>}</td></tr>)}</tbody></table></div></Panel></section>
}

function Records({ analysis, onError }) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [detail, setDetail] = useState(null)
  if (!analysis) return <EmptyState title="No record changes" text="Run an analysis to inspect record-level differences." />
  const allRecords = recordLists(analysis)
  const records = allRecords.filter((record) => (category === 'all' || record.change_category === category) && JSON.stringify(record).toLowerCase().includes(search.toLowerCase()))
  async function openRecord(record) {
    try { setDetail({ loading: true }); setDetail({ data: await getRecord(analysis.analysis_id, record.record_id) }) } catch (error) { onError(error); setDetail(null) }
  }
  return <section className="page-section"><PageIntro eyebrow="RECORD DIFF INSPECTOR" title="Inspect returned change categories" text="The analysis response is paginated. Search covers only the records returned in its current page; pagination metadata is shown below." /><div className="toolbar"><label className="search-field"><Search size={16} /><input placeholder="Search record ID or name" value={search} onChange={(event) => setSearch(event.target.value)} /></label><FilterSelect label="Category" value={category} onChange={setCategory} options={['all', 'ADDED', 'DELETED', 'MODIFIED', 'UNCHANGED', 'AMBIGUOUS']} /></div><Panel title={`${records.length} returned records`}><div className="table-scroll"><table><thead><tr><th>Record ID</th><th>Category</th><th>Area</th><th>Changed fields</th><th /></tr></thead><tbody>{records.map((record) => <tr key={`${record.record_id}-${record.change_category}`}><td><strong>{record.record_id || 'Not available'}</strong></td><td><span className={`category-pill ${record.change_category?.toLowerCase()}`}>{record.change_category}</span></td><td>{record.data?.area_id || record.current_values?.area_id || record.previous_values?.area_id || '—'}</td><td>{record.changed_fields?.join(', ') || (record.change_category === 'ADDED' ? 'New record' : '—')}</td><td><button className="mini-button" onClick={() => openRecord(record)}>Inspect</button></td></tr>)}</tbody></table></div><div className="pagination-note">Added page {analysis.changes?.added_records?.page || 1} of {analysis.changes?.added_records?.total_pages || 1}; deleted page {analysis.changes?.deleted_records?.page || 1} of {analysis.changes?.deleted_records?.total_pages || 1}; modified page {analysis.changes?.modified_records?.page || 1} of {analysis.changes?.modified_records?.total_pages || 1}.</div></Panel>{detail?.data && <RecordDrawer detail={detail.data} onClose={() => setDetail(null)} />}</section>
}

function RecordDrawer({ detail, onClose }) {
  const previous = detail.previous_values || {}
  const current = detail.current_values || {}
  const fields = [...new Set([...Object.keys(previous), ...Object.keys(current)])]
  return <div className="drawer-backdrop" onClick={onClose}><aside className="record-drawer" onClick={(event) => event.stopPropagation()}><button className="close-button" onClick={onClose}><X size={18} /></button><span className="eyebrow">RECORD DETAIL</span><h2>{detail.record_id}</h2><span className={`category-pill ${detail.change_category?.toLowerCase()}`}>{detail.change_category}</span><div className="diff-grid">{fields.map((field) => <div key={field} className={detail.changed_fields?.includes(field) ? 'diff-row changed' : 'diff-row'}><strong>{field}</strong><span>{valueOrUnavailable(previous[field])}</span><span>→</span><span>{valueOrUnavailable(current[field])}</span></div>)}</div><ListBlock title="Recommended review actions" items={detail.recommended_review_actions || []} /><ListBlock title="Related findings" items={detail.related_findings || []} /></aside></div>
}

function Counterfactual({ analysis, saved, onSave, onError }) {
  const [area, setArea] = useState(analysis?.area_comparison?.[0]?.area_id || '')
  const [method, setMethod] = useState('all_areas')
  const [threshold, setThreshold] = useState('20')
  async function run() {
    if (!analysis) return
    try { const result = await compareAreas({ analysis_id: analysis.analysis_id, area_id: area, comparison_method: method, threshold_override: Number(threshold) }); onSave(result) } catch (error) { onError(error) }
  }
  if (!analysis) return <EmptyState title="No counterfactual available" text="Run an analysis first." />
  return <section className="page-section"><PageIntro eyebrow="COUNTERFACTUAL AUDIT LAB" title="Change the comparison lens" text="This tool recomputes an area comparison using the backend's supplied rates and thresholds. It does not establish cause." /><Panel title="Simulation inputs"><div className="form-grid"><label>Area<select value={area} onChange={(event) => setArea(event.target.value)}>{analysis.area_comparison?.map((item) => <option key={item.area_id}>{item.area_id}</option>)}</select></label><label>Comparison method<select value={method} onChange={(event) => setMethod(event.target.value)}><option value="all_areas">All other areas</option><option value="similar_areas">Similar areas</option></select></label><label>Threshold (percentage points)<input type="number" min="0.01" step="0.01" value={threshold} onChange={(event) => setThreshold(event.target.value)} /></label></div><button className="button primary" onClick={run}><SlidersHorizontal size={17} /> Run comparison</button></Panel>{saved && <Panel title="Result"><div className="result-banner"><strong>{saved.new_comparison?.flagged ? 'Flagged under this comparison' : 'Not flagged under this comparison'}</strong><span>{saved.explanation}</span></div>{saved.warnings?.map((warning) => <div className="inline-warning" key={warning}><AlertTriangle size={15} />{warning}</div>)}<div className="metric-grid compact-grid"><MetricCard label="Removal rate" value={formatPercent(saved.removal_rate_pct)} tone="navy" /><MetricCard label="New baseline" value={formatPercent(saved.new_comparison?.baseline_rate_pct)} tone="blue" /><MetricCard label="Group size" value={saved.new_comparison?.group_size} tone="green" /></div></Panel>}</section>
}

function Assistant({ analysis, selectedFinding, onError, onOpenChat }) {
  const [findingId, setFindingId] = useState(selectedFinding?.finding_id || analysis?.findings?.[0]?.finding_id || '')
  const [question, setQuestion] = useState('why_flagged')
  const [language, setLanguage] = useState('simple')
  const [answer, setAnswer] = useState(null)
  async function ask() {
    if (!analysis || !findingId) return
    try { setAnswer(await explainQuestion({ analysis_id: analysis.analysis_id, finding_id: findingId, question_key: question, language })) } catch (error) { onError(error) }
  }
  if (!analysis) return <EmptyState title="Assistant needs an analysis" text="Upload data and select a finding first." />
  return (
    <section className="page-section">
      <div className="chat-promo-banner">
        <div className="chat-promo-text">
          <div className="promo-badge"><Sparkles size={14} /> Bilingual AI & Hybrid Engine</div>
          <h3>Conversational Electoral Roll Assistant</h3>
          <p>Get holistic roll summaries, ask comparative questions in English or Hindi, and inspect anomaly evidence interactively.</p>
        </div>
        <button className="button primary" onClick={onOpenChat}><MessageSquare size={16} /> Open Conversational Assistant</button>
      </div>
      <PageIntro eyebrow="MULTILINGUAL ASSISTANT" title="Ask about an API-returned finding" text="Answers are deterministic templates from the backend. They do not identify people, attribute intent, or prove wrongdoing." />
      <Panel title="Question controls">
        <div className="form-grid">
          <label>Finding<select value={findingId} onChange={(event) => setFindingId(event.target.value)}>{analysis.findings?.map((finding) => <option key={finding.finding_id} value={finding.finding_id}>{finding.finding_id}</option>)}</select></label>
          <label>Question<select value={question} onChange={(event) => setQuestion(event.target.value)}><option value="why_flagged">Why was this flagged?</option><option value="what_evidence">What evidence supports it?</option><option value="what_percentage">What does the percentage mean?</option><option value="what_verify">What should a reviewer verify?</option><option value="does_prove_wrongdoing">Does this prove wrongdoing?</option></select></label>
          <label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="simple">Simple English</option><option value="technical">Technical</option><option value="hindi">Hindi</option></select></label>
        </div>
        <div className="example-question">Example limitation question: “Who committed fraud?” → This evidence cannot identify a person or establish wrongdoing.</div>
        <button className="button primary" onClick={ask}><Languages size={17} /> Ask backend</button>
      </Panel>
      {answer && <Panel title="Backend answer"><div className="answer-box"><span className="answer-label">{answer.language} · {answer.question_key}</span><p>{answer.answer}</p></div></Panel>}
    </section>
  )
}

function Benchmark({ onError }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  async function run() { setLoading(true); try { setResult(await runChallenge()) } catch (error) { onError(error) } finally { setLoading(false) } }
  const scenarios = Array.isArray(result?.scenario_results) ? result.scenario_results : []
  return <section className="page-section"><PageIntro eyebrow="FALSE-ALARM BENCHMARK" title="Ten controlled synthetic scenarios" text="Metrics below come directly from POST /api/challenge/run. They are not a guarantee of real-world electoral performance." /><button className="button primary" disabled={loading} onClick={run}>{loading ? <><RefreshCw className="spin" size={17} /> Running…</> : <><FlaskConical size={17} /> Run benchmark</>}</button>{result && <><div className="metric-grid benchmark-grid">{[['Total scenarios', result.total_scenarios], ['Passed', result.passed], ['Failed', result.failed], ['Precision', result.precision == null ? 'Not calculable' : `${(result.precision * 100).toFixed(1)}%`], ['Recall', result.recall == null ? 'Not calculable' : `${(result.recall * 100).toFixed(1)}%`]].map(([label, value]) => <MetricCard key={label} label={label} value={value} tone="blue" />)}</div><Panel title="Confusion counts"><div className="confusion-grid"><DataLine label="True positives" value={result.true_positives} /><DataLine label="True negatives" value={result.true_negatives} /><DataLine label="False positives" value={result.false_positives} /><DataLine label="False negatives" value={result.false_negatives} /></div>{result.disclaimer && <p className="muted">{result.disclaimer}</p>}{result.precision_note && <p className="muted">{result.precision_note}</p>}</Panel><Panel title="Scenario results"><div className="table-scroll"><table><thead><tr><th>ID</th><th>Description</th><th>Expected</th><th>Predicted</th><th>Outcome</th><th>Notes</th></tr></thead><tbody>{scenarios.map((scenario) => <tr key={scenario.scenario_id}><td><strong>{scenario.scenario_id}</strong></td><td>{scenario.description || 'Not supplied'}</td><td>{scenario.expected || 'Not supplied'}</td><td>{scenario.predicted || 'Not supplied'}</td><td><span className="status-text">{scenario.outcome || 'Not supplied'}</span></td><td>{scenario.notes || 'Not supplied'}</td></tr>)}</tbody></table></div>{!scenarios.length && <p className="muted">No scenario results were returned.</p>}</Panel></>}</section>
}

function Reports({ analysis, onError }) {
  const reports = [['summary', 'Summary report'], ['added', 'Added records'], ['deleted', 'Deleted records'], ['modified', 'Modified records'], ['findings', 'Findings log'], ['area_comparison', 'Area comparison']]
  async function download(type) { try { const result = await downloadExport(analysis.analysis_id, type); const url = URL.createObjectURL(result.blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = result.filename; anchor.click(); URL.revokeObjectURL(url) } catch (error) { onError(error) } }
  if (!analysis) return <EmptyState title="No reports available" text="Run an analysis to enable CSV exports." />
  return <section className="page-section"><PageIntro eyebrow="REPORTS & EXPORTS" title="Download the current analysis" text="These are backend-generated CSV reports for the active analysis. Exported record reports may contain uploaded fields." /><div className="report-grid">{reports.map(([type, label]) => <div className="report-card" key={type}><FileSpreadsheet size={20} /><div><h3>{label}</h3><span>{type}.csv</span></div><button className="icon-button" aria-label={`Download ${label}`} onClick={() => download(type)}><Download size={17} /></button></div>)}</div></section>
}

function PageIntro({ eyebrow, title, text }) { return <div className="page-intro"><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{text}</p></div> }
function Panel({ title, children, className = '' }) { return <section className={`panel ${className}`}><div className="panel-title"><h3>{title}</h3></div>{children}</section> }
function MetricCard({ label, value, tone }) { return <div className={`metric-card ${tone}`}><span>{label}</span><strong>{typeof value === 'string' ? value : formatNumber(value)}</strong></div> }
function DataLine({ label, value }) { return <div className="data-line"><span>{label}</span><strong>{formatNumber(value)}</strong></div> }
function InfoTile({ icon, title, text }) { return <div className="info-tile"><div className="info-icon">{icon}</div><div><strong>{title}</strong><p>{text}</p></div></div> }
function FilterSelect({ label, value, onChange, options }) { return <label className="filter-select"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option} value={option}>{option === 'all' ? 'All' : option.replaceAll('_', ' ')}</option>)}</select></label> }
function FindingsTable({ findings, onSelect }) { return <div className="table-scroll"><table><thead><tr><th>Finding</th><th>Priority</th><th>Metric</th><th>Baseline</th><th>Threshold</th></tr></thead><tbody>{findings.map((finding) => <tr key={finding.finding_id} onClick={() => onSelect(finding)} className="clickable-row"><td><strong>{finding.title}</strong><small>{finding.finding_id}</small></td><td><span className={`priority ${finding.review_priority?.toLowerCase()}`}>{finding.review_priority}</span></td><td>{formatPercent(findingMetric(finding))}</td><td>{formatPercent(finding.baseline)}</td><td>{finding.threshold == null ? 'Not available' : finding.threshold}</td></tr>)}</tbody></table></div> }
function InfoRow({ label, value, code = false }) { return <div className="info-row"><span>{label}</span>{code ? <pre>{value}</pre> : <p>{value}</p>}</div> }
function ListBlock({ title, items }) { return <div className="list-block"><strong>{title}</strong>{items.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="muted">Not supplied by the backend.</p>}</div> }
function NoticeText({ text }) { return <div className="passport-notice"><AlertTriangle size={15} />{text}</div> }
function EmptyState({ title, text, action, onAction }) { return <div className="empty-state"><Database size={26} /><h2>{title}</h2><p>{text}</p>{action && <button className="button secondary" onClick={onAction}>{action}</button>}</div> }
function valueOrUnavailable(value) { return value === undefined || value === null || value === '' ? 'Not available' : String(value) }
let nextChatMessageId = 0
function nextChatId(prefix) {
  nextChatMessageId += 1
  return `${prefix}-${nextChatMessageId}`
}
function chatMessageRecord(id, role, text, extra = {}) {
  return {
    id,
    role,
    text,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    ...extra,
  }
}
function formatRecordResult(result) {
  const changed = result.changed_fields?.length ? result.changed_fields.join(', ') : 'no changed fields'
  return `Record ${result.record_id} is ${result.change_category}. Changed fields: ${changed}. Review actions: ${(result.recommended_review_actions || []).join(' ') || 'not supplied by the backend.'}`
}
function formatCalculation(finding) {
  const evidence = finding.supporting_evidence || {}
  const observed = finding.baseline == null ? 'not available' : `${finding.baseline}`
  const threshold = finding.threshold == null ? 'not available' : `${finding.threshold}`
  return `${finding.title} (${finding.finding_id}). Observed evidence: ${JSON.stringify(evidence)}. Baseline: ${observed}. Threshold: ${threshold}. These values are reported for review; missing denominator or rule details are not inferred.`
}
function InsightAssistantChat({ analysis, isOpen, onToggle, onNavigate, onLoadSample, isAppLoading, selectedFinding, page, onSelectFinding, onApplyDraftEdit, onUndoDraftEdit, onDownloadDraft, draftHistory }) {
  const [language, setLanguage] = useState('en')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [allowExternalAi, setAllowExternalAi] = useState(true)
  const [pendingEdit, setPendingEdit] = useState(null)
  const [actionNotice, setActionNotice] = useState(null)
  const [loadedAnalysisKey, setLoadedAnalysisKey] = useState(null)
  const messagesEndRef = useRef(null)
  const shortcutRecordId = recordLists(analysis || {}).find((record) => record.record_id)?.record_id

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Load deterministic summary when chat is open and analysis is present
  const loadSummary = useCallback(async (analysisId, lang) => {
    setLoading(true)
    try {
      const res = await chatExplain(analysisId, lang)
      setLoadedAnalysisKey(`${analysisId}-${lang}`)
      setMessages([
        {
          ...chatMessageRecord(nextChatId('summary'), 'assistant', res.summary, {
            disclaimer: res.disclaimer,
            source: res.source,
            suggestedQuestions: res.suggested_questions || [],
            evidenceReferences: res.evidence_references || [],
          }),
        },
      ])
    } catch (err) {
      setMessages([
        {
          ...chatMessageRecord(nextChatId('err'), 'assistant', `Unable to load analysis summary: ${err.message}`, { isError: true }),
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen && analysis?.analysis_id) {
      const currentKey = `${analysis.analysis_id}-${language}`
      if (loadedAnalysisKey !== currentKey) {
        const timer = window.setTimeout(() => loadSummary(analysis.analysis_id, language), 0)
        return () => window.clearTimeout(timer)
      }
    }
  }, [isOpen, analysis?.analysis_id, language, loadedAnalysisKey, loadSummary])

  async function sendMessage(text) {
    const q = (text || input).trim()
    if (!q || !analysis?.analysis_id || loading) return

    const parsedAction = parseAssistantCommand(q, selectedFinding?.finding_id)
    const actionCheck = parsedAction && validateAssistantAction(parsedAction, { analysis, page, hasConfirmedDraft: draftHistory.length > 0 })
    if (parsedAction && !actionCheck.valid) {
      setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', actionCheck.message, { isError: true })])
      setInput('')
      return
    }
    if (parsedAction) {
      setMessages((prev) => [...prev, chatMessageRecord(nextChatId('u'), 'user', q)])
      setInput('')
      await executeAssistantAction(parsedAction)
      return
    }

    const userMessage = chatMessageRecord(nextChatId('u'), 'user', q)

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const res = await chatMessage(analysis.analysis_id, q, language, conversationId, allowExternalAi)
      if (res.conversation_id) setConversationId(res.conversation_id)

      const botMessage = chatMessageRecord(nextChatId('a'), 'assistant', res.answer, {
        disclaimer: res.disclaimer,
        source: res.source,
        suggestedQuestions: res.suggested_questions || [],
        evidenceReferences: res.evidence_references || [],
      })
      setMessages((prev) => [...prev, botMessage])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          ...chatMessageRecord(nextChatId('err'), 'assistant', `Chat request failed: ${err.message}`, { isError: true }),
        },
      ])
    } finally {
      setLoading(false)
    }

    async function executeAssistantAction(action) {
      try {
        if (action.type === ASSISTANT_ACTIONS.NAVIGATE_TO) {
          onNavigate(action.payload.page)
          setActionNotice('Opened the requested section.')
        } else if (action.type === ASSISTANT_ACTIONS.SHOW_FINDINGS) {
          onNavigate('findings')
          setActionNotice(`${analysis.findings?.length || 0} findings are available in the Findings section.`)
        } else if (action.type === ASSISTANT_ACTIONS.SELECT_FINDING) {
          const finding = action.payload.highestPriority ? highestFinding(analysis.findings) : selectedFinding
          if (!finding) throw new Error('No finding is available in this analysis.')
          onSelectFinding(finding)
          setActionNotice(`Opened ${finding.finding_id}. Priority is shown for review routing, not proof of cause.`)
        } else if (action.type === ASSISTANT_ACTIONS.SELECT_AREA) {
          const area = (analysis.area_comparison || []).find((item) => item.area_id.toUpperCase() === action.payload.areaId)
          if (!area) throw new Error(`Area ${action.payload.areaId} was not found in the active analysis.`)
          const areaFinding = analysis.findings?.find((finding) => finding.affected_area_id === area.area_id)
          if (areaFinding) onSelectFinding(areaFinding)
          else onNavigate('areas')
          setActionNotice(`${area.area_name} (${area.area_id}) is available with its returned area metrics${areaFinding ? ` and finding ${areaFinding.finding_id}` : ''}.`)
        } else if (action.type === ASSISTANT_ACTIONS.COMPARE_AREA) {
          const area = (analysis.area_comparison || []).find((item) => item.area_id.toUpperCase() === action.payload.areaId)
          if (!area) throw new Error(`Area ${action.payload.areaId} was not found in the active analysis.`)
          const result = await compareAreas({ analysis_id: analysis.analysis_id, area_id: area.area_id, comparison_method: 'all_areas' })
          onNavigate('counterfactual')
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', `Comparison for ${area.area_name} (${area.area_id}) completed using all other areas. ${result.explanation || 'See Counterfactual Audit Lab for the returned rates.'}`, { actionResult: result })])
      } else if (action.type === ASSISTANT_ACTIONS.OPEN_EVIDENCE) {
          const finding = analysis.findings?.find((item) => item.finding_id === action.payload.findingId)
          if (!finding) throw new Error('That finding is no longer available in the active analysis.')
          onSelectFinding(finding)
          setActionNotice(`Opened the evidence context for ${finding.finding_id}.`)
        } else if (action.type === ASSISTANT_ACTIONS.INSPECT_RECORD) {
          const result = await getRecord(analysis.analysis_id, action.payload.recordId)
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', formatRecordResult(result), { actionResult: result })])
        } else if (action.type === ASSISTANT_ACTIONS.RECHECK_FINDING) {
          const findingId = action.payload.findingId || selectedFinding?.finding_id
          if (!findingId) throw new Error('Select a finding first, then ask me to recheck it.')
          const result = await recheckFinding({ analysis_id: analysis.analysis_id, finding_id: findingId })
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', `Recheck completed for ${findingId}. Match: ${result.match === null ? 'not available' : result.match ? 'yes' : 'no'}. Dataset changed: ${result.dataset_changed ? 'yes' : 'no'}.`, { actionResult: result })])
        } else if (action.type === ASSISTANT_ACTIONS.EXPORT_REPORT) {
          const result = await downloadExport(analysis.analysis_id, action.payload.reportType)
          const url = URL.createObjectURL(result.blob)
          const anchor = document.createElement('a')
          anchor.href = url; anchor.download = result.filename; anchor.click(); URL.revokeObjectURL(url)
          setActionNotice(`${action.payload.reportType} report download started.`)
      } else if (action.type === ASSISTANT_ACTIONS.EXPORT_DRAFT) {
          onDownloadDraft()
          setActionNotice('Revised synthetic CSV download started. It contains the confirmed draft revision only.')
        } else if (action.type === ASSISTANT_ACTIONS.EXPLAIN_CALCULATION) {
          const finding = analysis.findings?.find((item) => item.finding_id === action.payload.findingId) || selectedFinding
          if (!finding) throw new Error('Select a finding to explain its calculation.')
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', formatCalculation(finding))])
      } else if (action.type === ASSISTANT_ACTIONS.RUN_COUNTERFACTUAL) {
          const areaId = action.payload.areaId || analysis.area_comparison?.[0]?.area_id
          if (!areaId) throw new Error('No area is available for a what-if comparison.')
          const result = await compareAreas({ analysis_id: analysis.analysis_id, area_id: areaId, comparison_method: 'all_areas', threshold_override: action.payload.threshold })
          onNavigate('counterfactual')
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', `What-if comparison for ${areaId} at ${action.payload.threshold}% completed. ${result.explanation || 'See Counterfactual Audit Lab for the returned comparison.'}`, { actionResult: result })])
        } else if (action.type === ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT) {
          const record = await getRecord(analysis.analysis_id, action.payload.recordId)
          const currentValue = record.current_values?.[action.payload.field] ?? record.previous_values?.[action.payload.field] ?? ''
          setPendingEdit({ ...action.payload, previousValue: currentValue })
        } else if (action.type === ASSISTANT_ACTIONS.UNDO_RECORD_EDIT) {
          await onUndoDraftEdit()
          setActionNotice('Last confirmed draft change undone. The prior draft is current.')
        } else if (action.type === ASSISTANT_ACTIONS.SHOW_CHANGE_HISTORY) {
          const historyText = draftHistory.length
            ? draftHistory.map((change, index) => `${index + 1}. ${change.recordId}.${change.field}: ${valueOrUnavailable(change.previousValue)} → ${valueOrUnavailable(change.nextValue)}`).join('\n')
            : 'No confirmed draft changes in this session.'
          setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', historyText)])
        } else if (action.type === ASSISTANT_ACTIONS.CLEAR_CHAT) {
          setMessages([])
          setConversationId(null)
          setActionNotice('Conversation cleared. The active analysis and draft are unchanged.')
        }
      } catch (error) {
        setMessages((prev) => [...prev, chatMessageRecord(nextChatId('err'), 'assistant', error.message || 'The requested operation could not be completed.', { isError: true })])
      }
    }

  }

  async function confirmEdit() {
    try {
      await onApplyDraftEdit(pendingEdit)
      setMessages((prev) => [...prev, chatMessageRecord(nextChatId('a'), 'assistant', `Draft revision applied for ${pendingEdit.recordId}. This is not an official electoral-roll update.`)])
      setActionNotice(`Draft revision applied for ${pendingEdit.recordId}. Original files remain unchanged.`)
      setPendingEdit(null)
    } catch (error) {
      setActionNotice(`Draft analysis failed: ${error.message}. The draft file is retained, but no analysis is current.`)
    }
  }

  function handleReset() {
    setConversationId(null)
    if (analysis?.analysis_id) {
      loadSummary(analysis.analysis_id, language)
    } else {
      setMessages([])
    }
  }

  function toggleLanguage() {
    const nextLang = language === 'en' ? 'hi' : 'en'
    setLanguage(nextLang)
    if (analysis?.analysis_id) {
      loadSummary(analysis.analysis_id, nextLang)
    }
  }

  return (
    <>
      <button
        className={`chat-fab ${isOpen ? 'active' : ''}`}
        onClick={onToggle}
        aria-label={isOpen ? 'Close Insight Assistant' : 'Open Insight Assistant'}
      >
        {isOpen ? <X size={20} /> : (
          <>
            <Sparkles size={18} />
            <span className="fab-label">Insight Assistant</span>
            {analysis && <span className="fab-pulse" />}
          </>
        )}
      </button>

      {isOpen && (
        <aside className="chat-window" aria-label="Insight Assistant Chat">
          <header className="chat-header">
            <div className="chat-header-info">
              <div className="chat-title-row">
                <Bot size={18} className="bot-icon" />
                <strong>Insight Assistant</strong>
                <span className="bilingual-badge">{language === 'hi' ? 'सहायक' : 'AI + Rules'}</span>
              </div>
              <div className="chat-subtitle">
                {analysis?.analysis_id ? (
                  <span className="active-id">Analysis: {analysis.analysis_id}</span>
                ) : (
                  <span>No active audit dataset</span>
                )}
              </div>
            </div>

            <div className="chat-header-actions">
              <button
                className="lang-toggle-btn"
                onClick={toggleLanguage}
                title={`Switch to ${language === 'en' ? 'Hindi' : 'English'}`}
              >
                <Globe size={14} />
                <span>{language === 'en' ? 'HI / हिंदी' : 'EN / English'}</span>
              </button>
              {analysis && (
                <button className="icon-btn-ghost" onClick={handleReset} title="Reset conversation">
                  <RotateCcw size={15} />
                </button>
              )}
              <button className="icon-btn-ghost" onClick={onToggle} title="Close chat">
                <X size={17} />
              </button>
            </div>
          </header>

          <div className="chat-disclaimer-bar">
            <AlertTriangle size={13} />
            <span>Signals for review only · Does not declare fraud or identify individuals</span>
          </div>
          <div className="chat-context-strip">
            <span>Context: {page.replaceAll('_', ' ')}</span>
            {selectedFinding && <span>Finding: {selectedFinding.finding_id}</span>}
            {draftHistory.length > 0 && <span>Draft changes: {draftHistory.length}</span>}
          </div>
          <label className="chat-ai-opt-in">
            <input type="checkbox" checked={allowExternalAi} onChange={(event) => setAllowExternalAi(event.target.checked)} />
            <span>Allow optional external AI for this chat. Aggregate audit facts may be sent to the configured provider.</span>
          </label>

          <div className="chat-body">
            {!analysis ? (
              <div className="chat-empty-state">
                <Database size={32} />
                <h4>No Electoral Roll Analyzed Yet</h4>
                <p>Run a comparison between previous and current rolls to unlock conversational insights, area anomaly explanations, and bilingual audit guidance.</p>
                <button className="button primary sm" disabled={isAppLoading} onClick={() => { onLoadSample(); }}>
                  {isAppLoading ? <><RefreshCw className="spin" size={14} /> Loading Demo Datasets…</> : <><FolderOpen size={15} /> Load Demo Datasets</>}
                </button>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <div key={msg.id} className={`chat-message-bubble ${msg.role}`}>
                    <div className="msg-header">
                      <span className="sender-name">
                        {msg.role === 'assistant' ? (
                          <>
                            <Sparkles size={13} />
                            {msg.source === 'ai_gemini' ? 'Gemini AI' : 'VoterLens Engine (Deterministic)'}
                          </>
                        ) : (
                          <>
                            <User size={13} /> You
                          </>
                        )}
                      </span>
                      <span className="msg-time">{msg.timestamp}</span>
                    </div>

                    <div className="msg-content">
                      <ChatFormattedText text={msg.text} />
                    </div>

                    {msg.isError && (
                      <div style={{ marginTop: '8px' }}>
                        <button
                          className="mini-button"
                          onClick={() => {
                            setLoadedAnalysisKey(null)
                            loadSummary(analysis.analysis_id, language)
                          }}
                        >
                          <RotateCcw size={12} /> Retry Loading Summary
                        </button>
                      </div>
                    )}

                    {msg.evidenceReferences && msg.evidenceReferences.length > 0 && (
                      <div className="evidence-chips">
                        <span className="evidence-title">Related Evidence:</span>
                        <div className="evidence-pills-row">
                          {msg.evidenceReferences.map((ref, idx) => (
                            <button
                              key={`${ref.id}-${idx}`}
                              className="evidence-pill"
                              onClick={() => {
                                if (ref.type === 'area') onNavigate('areas')
                                else if (ref.type === 'finding') onNavigate('findings')
                              }}
                              title={`Jump to ${ref.type}`}
                            >
                              <span>{ref.label || ref.id}</span>
                              <ExternalLink size={11} />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {msg.disclaimer && (
                      <div className="msg-disclaimer">
                        <small>{msg.disclaimer}</small>
                      </div>
                    )}

                    {msg.suggestedQuestions && msg.suggestedQuestions.length > 0 && (
                      <div className="suggested-chips-block">
                        <span className="suggested-title">Suggested questions:</span>
                        <div className="suggested-chips-list">
                          {msg.suggestedQuestions.map((sq, i) => (
                            <button
                              key={i}
                              className="suggested-chip"
                              onClick={() => sendMessage(sq)}
                              disabled={loading}
                            >
                              <CornerDownRight size={12} />
                              <span>{sq}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {pendingEdit && (
                  <div className="chat-action-card" role="dialog" aria-label="Confirm draft edit">
                    <strong>Confirm draft revision</strong>
                    <p>{pendingEdit.recordId}: <code>{pendingEdit.field}</code> from <strong>{valueOrUnavailable(pendingEdit.previousValue)}</strong> to <strong>{pendingEdit.value}</strong></p>
                    <small>Only the current synthetic draft will change. The original file stays unchanged and the audit will run again.</small>
                    <div className="action-row">
                      <button className="button primary sm" onClick={confirmEdit}>Confirm change</button>
                      <button className="button secondary sm" onClick={() => setPendingEdit(null)}>Cancel</button>
                    </div>
                  </div>
                )}
                {actionNotice && <div className="chat-action-result" role="status">{actionNotice}<button className="text-button" onClick={() => setActionNotice(null)}>Dismiss</button></div>}
                {draftHistory.length > 0 && (
                  <button className="button secondary sm draft-export-button" type="button" onClick={() => {
                    try { onDownloadDraft(); setActionNotice('Revised synthetic CSV download started.') } catch (error) { setActionNotice(error.message) }
                  }}>
                    <Download size={14} /> Download revised synthetic CSV
                  </button>
                )}

                {loading && (
                  <div className="chat-message-bubble assistant loading">
                    <div className="msg-header">
                      <span className="sender-name"><Sparkles size={13} /> Analyzing roll...</span>
                    </div>
                    <div className="typing-dots">
                      <span /><span /><span />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {analysis && (
            <footer className="chat-footer">
              <form
                className="chat-input-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  sendMessage()
                }}
              >
                <div className="input-row">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value.slice(0, 500))}
                    placeholder={
                      language === 'hi'
                        ? 'मतदाता सूची, विसंगतियों या क्षेत्रों के बारे में पूछें...'
                        : 'Ask about findings, removal rates, data quality...'
                    }
                    disabled={loading}
                  />
                  <button
                    type="submit"
                    className="send-button"
                    disabled={!input.trim() || loading}
                    aria-label="Send message"
                  >
                    <Send size={16} />
                  </button>
                </div>
                <div className="chat-shortcuts">
                  {['Show findings', shortcutRecordId ? `What changed in record ${shortcutRecordId}?` : 'Show findings', 'Recheck this finding', 'Download findings report'].map((shortcut) => (
                    <button key={shortcut} className="suggested-chip" type="button" onClick={() => sendMessage(shortcut)} disabled={loading}>{shortcut}</button>
                  ))}
                </div>
                <div className="input-meta">
                  <span>{input.length}/500 chars</span>
                  <span className="privacy-tag">Never sends voter PII</span>
                </div>
              </form>
            </footer>
          )}
        </aside>
      )}
    </>
  )
}

function ChatFormattedText({ text }) {
  if (!text) return null
  const paragraphs = text.split('\n\n')

  return (
    <div className="formatted-chat-text">
      {paragraphs.map((p, idx) => {
        if (p.includes('\n- ') || p.includes('\n* ') || p.startsWith('- ') || p.startsWith('* ')) {
          const lines = p.split('\n').filter(Boolean)
          return (
            <ul key={idx}>
              {lines.map((line, lIdx) => (
                <li key={lIdx}>
                  <InlineBoldText text={line.replace(/^[-*]\s+/, '')} />
                </li>
              ))}
            </ul>
          )
        }
        if (/^\d+\.\s+/.test(p)) {
          const lines = p.split('\n').filter(Boolean)
          return (
            <ol key={idx}>
              {lines.map((line, lIdx) => (
                <li key={lIdx}>
                  <InlineBoldText text={line.replace(/^\d+\.\s+/, '')} />
                </li>
              ))}
            </ol>
          )
        }
        return (
          <p key={idx}>
            <InlineBoldText text={p} />
          </p>
        )
      })}
    </div>
  )
}

function InlineBoldText({ text }) {
  if (!text) return null
  const parts = text.split(/(\*\*.*?\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return part
  })
}

export default App
