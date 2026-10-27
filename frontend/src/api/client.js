const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const message = payload?.message || `Request failed with status ${response.status}`
    throw new Error(message)
  }
  return { payload, response }
}

export async function getHealth(signal) {
  const { payload } = await request('/api/health', { signal })
  return payload
}

export async function getSampleMetadata() {
  const { payload } = await request('/api/sample-data')
  return payload
}

export async function downloadSample(type) {
  const { payload } = await request(`/api/sample-data/${type}`)
  return new Blob([payload], { type: 'text/csv' })
}

export async function analyzeFiles(previousFile, currentFile) {
  const formData = new FormData()
  formData.append('previous_file', previousFile)
  formData.append('current_file', currentFile)
  const { payload } = await request('/api/analyze', { method: 'POST', body: formData })
  return payload
}

export async function compareAreas(body) {
  const { payload } = await request('/api/compare-areas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return payload
}

export async function recheckFinding(body) {
  const { payload } = await request('/api/recheck-finding', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return payload
}

export async function getRecord(analysisId, recordId) {
  const { payload } = await request(`/api/record/${encodeURIComponent(analysisId)}/${encodeURIComponent(recordId)}`)
  return payload
}

export async function explainQuestion(body) {
  const { payload } = await request('/api/explain-qa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return payload
}

export async function runChallenge() {
  const { payload } = await request('/api/challenge/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  return payload
}

export async function downloadExport(analysisId, reportType) {
  const { payload, response } = await request(`/api/export/${encodeURIComponent(analysisId)}/${reportType}`)
  const disposition = response.headers.get('content-disposition') || ''
  const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] || `voterlens-${reportType}.csv`
  return { blob: new Blob([payload], { type: 'text/csv' }), filename }
}

export { API_BASE_URL }
