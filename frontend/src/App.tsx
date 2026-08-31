import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'

type Dataset = { id: string; dataset_id?: string; name: string; source_type: string; quality_status: string; created_at: string; members?: unknown[] }
type Route = { id: string; name: string; direction?: string; stops: string[]; coordinates: number[][] }
type Metric = { scope_type: string; scope_id: string; metric_name: string; base_value: number; scenario_value: number; delta_value: number }
type DatasetDetail = Dataset & { mapping_status: string; files: { member_name: string; file_type: string; service_date?: string }[] }
type Mapping = { source_file_type: string; source_column: string; canonical_field: string; confidence: number }

const API = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

async function upload(path: string, file: File): Promise<Dataset> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`${API}${path}`, { method: 'POST', body })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState('')
  const [routes, setRoutes] = useState<Route[]>([])
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null)
  const [message, setMessage] = useState('데이터셋을 선택하거나 압축파일을 업로드하세요.')
  const [uploading, setUploading] = useState(false)
  const [metrics, setMetrics] = useState<Metric[]>([])
  const [datasetDetail, setDatasetDetail] = useState<DatasetDetail | null>(null)
  const [mappingSuggestions, setMappingSuggestions] = useState<Mapping[]>([])
  const [mappingConfirmed, setMappingConfirmed] = useState(false)
  const mapContainer = useRef<HTMLDivElement>(null)
  const [editMode, setEditMode] = useState(false)
  const [editedStops, setEditedStops] = useState<string[]>([])
  const [headway, setHeadway] = useState(600)
  const [serviceStart, setServiceStart] = useState('06:00')
  const [serviceEnd, setServiceEnd] = useState('23:00')

  const refresh = async () => {
    const items = await get<Dataset[]>('/datasets')
    setDatasets(items)
    if (!selectedDataset && items[0]) setSelectedDataset(items[0].id)
  }
  useEffect(() => { refresh().catch(error => setMessage(error.message)) }, [])
  useEffect(() => {
    if (!selectedDataset) return
    get<DatasetDetail>(`/datasets/${selectedDataset}`).then(setDatasetDetail).catch(error => setMessage(error.message))
    get<{ suggestions: Mapping[] }>(`/datasets/${selectedDataset}/mapping`).then(result => setMappingSuggestions(result.suggestions)).catch(error => setMessage(error.message))
    get<Route[]>(`/networks/${selectedDataset}/routes`).then(setRoutes).catch(error => setMessage(error.message))
  }, [selectedDataset])
  useEffect(() => {
    if (!selectedDataset || !mapContainer.current) return
    let map: maplibregl.Map | undefined
    get<{ type: 'FeatureCollection'; features: unknown[] }>(`/networks/${selectedDataset}/geojson`).then(geojson => {
      if (!mapContainer.current) return
      map = new maplibregl.Map({
        container: mapContainer.current,
        style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#e9eee8' } }] },
        center: [127.5, 35.0],
        zoom: 8,
        attributionControl: false,
      })
        map.on('load', () => {
          map?.addSource('routes', { type: 'geojson', data: geojson as never })
          map?.addLayer({ id: 'routes', type: 'line', source: 'routes', paint: { 'line-color': '#477b58', 'line-width': 3, 'line-opacity': .85 } })
          map?.addLayer({ id: 'stops', type: 'circle', source: 'routes', filter: ['==', ['get', 'feature_type'], 'stop'], paint: { 'circle-color': '#f2b84b', 'circle-radius': 4, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1 } })
        const coordinates = geojson.features.flatMap(feature => (feature as { geometry?: { coordinates?: number[][] } }).geometry?.coordinates ?? [])
        if (coordinates.length > 1) {
          const bounds = coordinates.reduce((current, coordinate) => current.extend(coordinate as [number, number]), new maplibregl.LngLatBounds(coordinates[0] as [number, number], coordinates[0] as [number, number]))
          map?.fitBounds(bounds, { padding: 45, maxZoom: 12 })
        }
      })
    }).catch(error => setMessage(error.message))
    return () => map?.remove()
  }, [selectedDataset])

  const selected = useMemo(() => datasets.find(item => item.id === selectedDataset), [datasets, selectedDataset])
  const startEdit = () => { if (selectedRoute) { setEditedStops([...selectedRoute.stops]); setHeadway(600); setServiceStart('06:00'); setServiceEnd('23:00'); setEditMode(true) } }
  const removeLastStop = () => setEditedStops(stops => stops.length > 2 ? stops.slice(0, -1) : stops)
  const saveScenario = async () => {
    if (!selectedRoute) return
    try {
      const changes = [{ change_type: 'REORDER_STOP', route_id: selectedRoute.id, stops: editedStops }, { change_type: 'CHANGE_HEADWAY', route_id: selectedRoute.id, headway_seconds: headway }, { change_type: 'CHANGE_SERVICE_WINDOW', route_id: selectedRoute.id, service_start_time: serviceStart, service_end_time: serviceEnd }]
      const response = await fetch(`${API}/scenarios`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: `${selectedRoute.id} 정류장 조정`, base_network_version: selectedDataset, changes }) })
      if (!response.ok) throw new Error(await response.text())
      const scenario = await response.json()
      const run = await fetch(`${API}/scenarios/${scenario.id}/run`, { method: 'POST' })
      if (!run.ok) throw new Error(await run.text())
      const detail = await get<Metric[]>(`/scenarios/${scenario.id}/metrics/detail`)
      setMetrics(detail.filter(item => item.scope_type === 'ROUTE' || item.scope_type === 'NETWORK'))
      setMessage(`시나리오 ${scenario.id} 실행 완료. Base와 Scenario 결과를 확인하세요.`)
      setEditMode(false)
    } catch (error) { setMessage(error instanceof Error ? error.message : '시나리오 실행 실패') }
  }
  const confirmMapping = async () => {
    try {
      const response = await fetch(`${API}/datasets/${selectedDataset}/mapping`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed: true, mappings: mappingSuggestions }) })
      if (!response.ok) throw new Error(await response.text())
      setMappingConfirmed(true)
      setMessage('표준 필드 매핑을 확정했습니다.')
    } catch (error) { setMessage(error instanceof Error ? error.message : '매핑 확정 실패') }
  }
  const handleUpload = async (kind: 'common' | 'daily', file?: File) => {
    if (!file) return
    setUploading(true)
    try {
      const result = await upload(`/datasets/uploads/${kind}`, file)
      setMessage(`${result.name ?? file.name} 업로드 완료. 내부 파일 ${result.members?.length ?? 0}개를 확인했습니다.`)
      await refresh()
      setSelectedDataset(result.dataset_id ?? result.id)
    } catch (error) { setMessage(error instanceof Error ? error.message : '업로드 실패') }
    finally { setUploading(false) }
  }

  return <div className="shell">
    <header><div><p className="eyebrow">TRANSIT / FIELD WORKSPACE</p><h1>지역 교통 수요 분석</h1></div><span className="status-dot">● API 연결 대기</span></header>
    <main>
      <section className="intro"><div><p className="eyebrow">01 · DATA INTAKE</p><h2>분석할 지역 데이터를 준비하세요</h2><p>공통코드와 일자별 ZIP을 각각 등록하면 품질을 확인한 뒤 지도에서 노선을 조정할 수 있습니다.</p></div><div className="upload-grid">
        <label className="upload-card"><strong>공통코드 ZIP</strong><span>COMMONCD.zip</span><input type="file" accept=".zip" onChange={event => handleUpload('common', event.target.files?.[0])} /></label>
        <label className="upload-card"><strong>일자별 데이터 ZIP</strong><span>DATA_YYYYMMDD.zip</span><input type="file" accept=".zip" onChange={event => handleUpload('daily', event.target.files?.[0])} /></label>
      </div></section>
      {uploading && <div className="notice">압축파일을 분석하고 있습니다...</div>}
      {datasetDetail && <div className="quality-strip"><strong>{datasetDetail.quality_status === 'passed' ? '✓ 품질검사 통과' : '⚠ 품질검사 확인 필요'}</strong><span>매핑 {datasetDetail.mapping_status}</span><span>내부 파일 {datasetDetail.files.length}개</span><span>{[...new Set(datasetDetail.files.map(file => file.service_date).filter(Boolean))].join(', ') || '공통코드'}</span></div>}
      {mappingSuggestions.length > 0 && <section className="mapping-card"><div><p className="eyebrow">MAPPING REVIEW</p><strong>원천 필드를 표준 분석 필드에 연결</strong><p>컬럼 번호별 자동 제안을 검토한 뒤 확정하세요. 현재 제안 {mappingSuggestions.length}개</p></div><button className="secondary light" onClick={confirmMapping}>{mappingConfirmed ? '매핑 확정됨' : '매핑 확정'}</button></section>}
      <section className="workspace">
        <aside className="panel datasets"><div className="panel-title"><span>데이터셋</span><small>{datasets.length}개 등록</small></div>{datasets.length === 0 && <p className="empty">아직 등록된 데이터가 없습니다.</p>}{datasets.map(dataset => <button className={`dataset ${dataset.id === selectedDataset ? 'active' : ''}`} key={dataset.id} onClick={() => setSelectedDataset(dataset.id)}><span><strong>{dataset.name}</strong><small>{dataset.source_type} · {dataset.id}</small></span><em className={dataset.quality_status}>{dataset.quality_status}</em></button>)}</aside>
        <section className="map-panel"><div className="panel-title"><span>현황 지도</span><small>{selected?.name ?? '데이터셋 미선택'}</small></div><div className="map-placeholder" ref={mapContainer}>{!selectedDataset && <div className="map-copy"><span className="map-pin">＋</span><strong>노선 지도를 불러올 준비가 되었습니다</strong><span>왼쪽에서 데이터셋을 선택하세요.</span></div>}</div></section>
        <aside className="panel routes"><div className="panel-title"><span>노선 목록</span><small>{routes.length}개</small></div>{routes.map(route => <button className={`route ${selectedRoute?.id === route.id ? 'active' : ''}`} key={route.id} onClick={() => setSelectedRoute(route)}><strong>{route.id}</strong><span>{route.name}</span><small>{route.stops.length}개 정류장</small></button>)}{routes.length === 0 && <p className="empty">검증된 일별 데이터를 선택하면 노선이 표시됩니다.</p>}</aside>
      </section>
      <section className="bottom"><div><p className="eyebrow">02 · SCENARIO</p><h2>{selectedRoute ? `${selectedRoute.id} 노선 조정` : '노선을 선택해 시나리오를 시작하세요'}</h2><p>{selectedRoute ? `${selectedRoute.name} · ${editMode ? editedStops.length : selectedRoute.stops.length}개 정류장` : '현황 지도에서 기존 노선의 정류장과 배차를 조정할 수 있습니다.'}</p>{editMode && <div className="edit-controls"><button className="secondary" onClick={removeLastStop}>마지막 정류장 삭제</button><label>배차 <input type="number" min="60" step="60" value={headway} onChange={event => setHeadway(Number(event.target.value))} />초</label><label>운행 <input type="time" value={serviceStart} onChange={event => setServiceStart(event.target.value)} /> ~ <input type="time" value={serviceEnd} onChange={event => setServiceEnd(event.target.value)} /></label></div>}</div><button className="primary" disabled={!selectedRoute} onClick={editMode ? saveScenario : startEdit}>{editMode ? '시나리오 저장·실행' : '노선 편집 시작'} <span>→</span></button></section>
      {metrics.length > 0 && <section className="results"><div className="panel-title"><span>Base vs Scenario</span><small>최근 실행 결과</small></div><table><thead><tr><th>범위</th><th>지표</th><th>Base</th><th>Scenario</th><th>변화</th></tr></thead><tbody>{metrics.map(metric => <tr key={`${metric.scope_type}-${metric.scope_id}-${metric.metric_name}`}><td>{metric.scope_id}</td><td>{metric.metric_name}</td><td>{metric.base_value.toFixed(1)}</td><td>{metric.scenario_value.toFixed(1)}</td><td className={metric.delta_value < 0 ? 'negative' : 'positive'}>{metric.delta_value > 0 ? '+' : ''}{metric.delta_value.toFixed(1)}</td></tr>)}</tbody></table></section>}
      <div className="message">{message}</div>
    </main>
  </div>
}
