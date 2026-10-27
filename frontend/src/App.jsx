import { useCallback, useEffect, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, Check, ChevronDown, ClipboardCheck,
  Database, Download, FileDiff, FileSpreadsheet, FlaskConical, FolderOpen,
  Languages, LayoutDashboard, Menu, RefreshCw, RotateCcw, Search, ShieldCheck,
  SlidersHorizontal, Upload, X, XCircle,
} from 'lucide-react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  analyzeFiles, compareAreas, downloadExport, downloadSample, explainQuestion,
  getHealth, getRecord, getSampleMetadata, recheckFinding, runChallenge,
} from './api/client'
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
          {page === 'assistant' && <Assistant analysis={workspace.analysis} selectedFinding={workspace.selectedFinding} onError={setError} />}
          {page === 'benchmark' && <Benchmark onError={setError} />}
          {page === 'reports' && <Reports analysis={workspace.analysis} onError={setError} />}
        </div>
      </main>
      {resetOpen && <ConfirmDialog onCancel={() => setResetOpen(false)} onConfirm={resetWorkspace} />}
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
  return <button className={`finding-card ${selected ? 'selected' : ''}`} onClick={onSelect}><div className="finding-card-top"><span className={`priority ${finding.review_priority?.toLowerCase()}`}>{finding.review_priority} review</span><span className="category-label">{finding.category === 'DATA_QUALITY' ? 'Data quality' : 'Area pattern'}</span></div><h3>{finding.title}</h3><p>{finding.description}</p><div className="finding-meta"><span>{finding.finding_id}</span><span>{finding.affected_record_count} record{finding.affected_record_count === 1 ? '' : 's'}</span>{finding.affected_area_id && <span>{finding.affected_area_id}</span>}</div><div className="finding-actions"><span>Open Evidence Passport →</span><button type="button" className="mini-button" onClick={(event) => { event.stopPropagation(); onRecheck() }} disabled={recheck?.loading}>{recheck?.loading ? 'Checking…' : 'Recheck'}</button>{recheck?.result && <span className={recheck.result.match ? 'recheck-pass' : 'recheck-fail'}>{recheck.result.match ? 'Match' : 'Mismatch'}</span>}</div>{recheck?.error && <span className="inline-error">{recheck.error}</span>}</button>
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

function Assistant({ analysis, selectedFinding, onError }) {
  const [findingId, setFindingId] = useState(selectedFinding?.finding_id || analysis?.findings?.[0]?.finding_id || '')
  const [question, setQuestion] = useState('why_flagged')
  const [language, setLanguage] = useState('simple')
  const [answer, setAnswer] = useState(null)
  async function ask() {
    if (!analysis || !findingId) return
    try { setAnswer(await explainQuestion({ analysis_id: analysis.analysis_id, finding_id: findingId, question_key: question, language })) } catch (error) { onError(error) }
  }
  if (!analysis) return <EmptyState title="Assistant needs an analysis" text="Upload data and select a finding first." />
  return <section className="page-section"><PageIntro eyebrow="MULTILINGUAL ASSISTANT" title="Ask about an API-returned finding" text="Answers are deterministic templates from the backend. They do not identify people, attribute intent, or prove wrongdoing." /><Panel title="Question controls"><div className="form-grid"><label>Finding<select value={findingId} onChange={(event) => setFindingId(event.target.value)}>{analysis.findings?.map((finding) => <option key={finding.finding_id} value={finding.finding_id}>{finding.finding_id}</option>)}</select></label><label>Question<select value={question} onChange={(event) => setQuestion(event.target.value)}><option value="why_flagged">Why was this flagged?</option><option value="what_evidence">What evidence supports it?</option><option value="what_percentage">What does the percentage mean?</option><option value="what_verify">What should a reviewer verify?</option><option value="does_prove_wrongdoing">Does this prove wrongdoing?</option></select></label><label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="simple">Simple English</option><option value="technical">Technical</option><option value="hindi">Hindi</option></select></label></div><div className="example-question">Example limitation question: “Who committed fraud?” → This evidence cannot identify a person or establish wrongdoing.</div><button className="button primary" onClick={ask}><Languages size={17} /> Ask backend</button></Panel>{answer && <Panel title="Backend answer"><div className="answer-box"><span className="answer-label">{answer.language} · {answer.question_key}</span><p>{answer.answer}</p></div></Panel>}</section>
}

function Benchmark({ onError }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  async function run() { setLoading(true); try { setResult(await runChallenge()) } catch (error) { onError(error) } finally { setLoading(false) } }
  return <section className="page-section"><PageIntro eyebrow="FALSE-ALARM BENCHMARK" title="Ten controlled synthetic scenarios" text="Metrics below come directly from POST /api/challenge/run. They are not a guarantee of real-world electoral performance." /><button className="button primary" disabled={loading} onClick={run}>{loading ? <><RefreshCw className="spin" size={17} /> Running…</> : <><FlaskConical size={17} /> Run benchmark</>}</button>{result && <><div className="metric-grid benchmark-grid">{[['Total scenarios', result.total_scenarios], ['Passed', result.passed], ['Failed', result.failed], ['Precision', result.precision == null ? 'Not calculable' : `${(result.precision * 100).toFixed(1)}%`], ['Recall', result.recall == null ? 'Not calculable' : `${(result.recall * 100).toFixed(1)}%`]].map(([label, value]) => <MetricCard key={label} label={label} value={value} tone="blue" />)}</div><Panel title="Confusion counts"><div className="confusion-grid"><DataLine label="True positives" value={result.true_positives} /><DataLine label="True negatives" value={result.true_negatives} /><DataLine label="False positives" value={result.false_positives} /><DataLine label="False negatives" value={result.false_negatives} /></div>{result.disclaimer && <p className="muted">{result.disclaimer}</p>}{result.precision_note && <p className="muted">{result.precision_note}</p>}</Panel><Panel title="Scenario results"><div className="table-scroll"><table><thead><tr><th>ID</th><th>Description</th><th>Expected</th><th>Predicted</th><th>Outcome</th><th>Notes</th></tr></thead><tbody>{(result.scenarios || []).map((scenario) => <tr key={scenario.scenario_id}><td><strong>{scenario.scenario_id}</strong></td><td>{scenario.description}</td><td>{scenario.expected}</td><td>{scenario.predicted}</td><td><span className="status-text">{scenario.outcome}</span></td><td>{scenario.notes}</td></tr>)}</tbody></table></div></Panel></>}</section>
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
function ConfirmDialog({ onCancel, onConfirm }) { return <div className="modal-backdrop"><div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="reset-title"><h2 id="reset-title">Reset client workspace?</h2><p>This clears selected files, findings, filters, and displayed analysis in this browser. It does not erase the backend's in-memory analysis store.</p><div className="action-row"><button className="button secondary" onClick={onCancel}>Cancel</button><button className="button danger" onClick={onConfirm}>Clear workspace</button></div></div></div> }

export default App
