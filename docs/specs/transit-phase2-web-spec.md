# Transit 2차 MVP 실행계획 및 기술 Spec

- 문서 상태: 승인됨
- 작성일: 2026-08-31
- 기준 문서: `docs/specs/transit-mvp-spec.md`, `docs/PRD_transit_analysis_bus_scenario.md`
- 목표: 실제 지역 데이터 업로드부터 지도 기반 기존 노선 조정 및 결과 비교까지 웹에서 재현

## 1. Context

Transit MVP는 교통카드·BIS 파일 등록, 수요 집계, 버스 시나리오 실행과 KPI 비교를 제공한다. 현재 사용자 인터페이스는 CLI이며 FastAPI에는 health와 조회 전용 API만 있다. 연구·교통 실무자가 실제 지역 데이터를 업로드하고 지도에서 노선을 조정하려면 웹 UI와 그에 필요한 업로드·매핑·시나리오 API가 필요하다.

2차 MVP의 완료 단위는 특정 지역 1곳이다. 사용자는 `COMMONCD.zip`과 여러 일자별 데이터 압축파일을 등록하고, 품질검사 후 기존 노선 1개를 조정한 시나리오를 실행해 Base와 Scenario 결과를 비교한다.

## 2. Current State

검증일: 2026-08-31

| 영역 | 현재 상태 | 2차 갭 |
|---|---|---|
| 입력 | `src/transit/ingest.py`의 CSV/Parquet 등록·정규화·검증 | 압축 내부 DAT, `|` 구분자, 공통코드, 여러 service date 지원 |
| 저장 | `src/transit/db.py`의 SQLite datasets/routes/stops/transactions/scenarios/metrics | 원천 파일 묶음, 매핑, 실행 snapshot 관리 |
| 현황 | `src/transit/pipeline.py`와 API 조회 구현 | 지도용 노선·정류장 GeoJSON 및 필터 |
| 시나리오 | `src/transit/scenarios.py`와 `pipeline.py`에서 변경·실행 | 웹 편집, draft, 상태 표시 |
| API | `src/transit/api/app.py:10-76`에 조회 endpoint 4개 | 업로드·매핑·노선·시나리오 CRUD/실행 |
| UI | 프론트엔드 없음. CLI는 `src/transit/cli.py:13-152` | React/TypeScript/MapLibre 웹 앱 |
| 테스트 | 15개 통과, 28개는 Windows pytest 임시 디렉터리 권한 오류로 setup 실패 | 저장소 내부 temp 경로 고정 |

실제 샘플은 `data/sample/common/COMMONCD.zip`과 `data/sample/daily/DATA_20240420.zip`이다. 공통 압축에는 코드 테이블과 `ColumnDefinition_20250320.xlsx`가 있으며, 일별 압축에는 `DWTCD`, `ROUTE`, `ROUTESTTN`, `STTN`이 있다. DAT 파일은 `|` 구분자다.

## 3. Scope

### 포함

- 공통코드 압축파일 각각 업로드
- 여러 일자별 데이터 압축파일 등록
- 압축 내부 파일 식별 및 DAT 파싱
- 컬럼 매핑, 품질검사, 오류 표시
- 지역 데이터의 노선·정류장·수요 저장
- 지도 기반 현황 조회
- 기존 노선의 정류장 추가·삭제·순서 변경
- 기존 노선의 배차간격·운행시간대 변경
- 시나리오 draft 저장·실행·상태 조회
- Base vs Scenario KPI 비교
- 실제 지역 1개, 노선 1개, 조정 시나리오 1개의 end-to-end 검증
- 기존 CLI와 조회 API 유지

### 제외

- 신규 노선 생성
- OSRM, OTP, 철도 GTFS 결합
- PostGIS 및 대용량 columnar 전환
- 비동기 worker, Redis, Celery
- 인증·다중 사용자 권한
- 고급 calibration, 혼잡 피드백, 자동 최적화
- XLSX/GeoPackage/GTFS export
- 클라우드 배포 및 운영 모니터링

## 4. User Flow

```text
COMMONCD.zip 업로드
        +
여러 DATA_YYYYMMDD.zip 업로드
        ↓
내부 파일 식별 → 표준 매핑 → 품질검사
        ↓
노선·정류장 현황 지도
        ↓
기존 노선 1개 정류장/배차 조정
        ↓
Draft 저장 → 실행 → Base/Scenario 비교
```

## 5. Architecture

```text
React + TypeScript + MapLibre
                ↓ HTTP/JSON
FastAPI upload/mapping/network/scenario API
                ↓
Region adapter + existing transit pipeline
                ↓
SQLite source/snapshot/metrics storage
```

프론트엔드는 `frontend/`에 신규 추가한다. 지도 편집은 정류장 목록과 지도 선택 상태를 함께 제공하고, 저장 전 변경은 draft로 표시한다. 2차에서는 기존 Python 실행 흐름을 동기 API로 연결하며, 장시간 작업용 worker는 후속 PoC로 둔다.

## 6. Data Model

기존 `datasets`, `scenarios`, `metric_results`는 유지한다. 다음 테이블을 추가한다.

```sql
CREATE TABLE dataset_files (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  archive_name TEXT NOT NULL,
  member_name TEXT NOT NULL,
  file_type TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  service_date TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);

CREATE TABLE dataset_mappings (
  dataset_id TEXT NOT NULL,
  source_file_type TEXT NOT NULL,
  source_column TEXT NOT NULL,
  canonical_field TEXT NOT NULL,
  confidence REAL NOT NULL,
  confirmed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (dataset_id, source_file_type, source_column),
  FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);

CREATE TABLE scenario_runs (
  id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','running','completed','failed')),
  base_snapshot TEXT NOT NULL,
  result_snapshot TEXT,
  error_code TEXT,
  error_message TEXT,
  started_at TEXT,
  completed_at TEXT,
  FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
);
```

원천 압축파일은 파일명, service date, SHA-256 hash와 함께 보존한다. 동일 hash는 중복 등록하지 않고 기존 데이터셋을 재사용하거나 명시적 중복 오류를 반환한다. 기준 네트워크와 원천 데이터는 시나리오 편집·실행으로 수정하지 않는다.

## 7. Regional Data Adapter

| 파일 | canonical 대상 |
|---|---|
| `ROUTE_YYYYMMDD.dat` | route_id, route_name, route_type, route_length, stop_count |
| `ROUTESTTN_YYYYMMDD.dat` | route_id, stop_sequence, stop_id, stop_name, latitude, longitude, distance_m, travel_time_s |
| `STTN_YYYYMMDD.dat` | stop_id, stop_name, latitude, longitude, region_code |
| `DWTCD_YYYYMMDD.dat` | transaction time, route, boarding/alighting stop, transfer fields |
| 공통코드 DAT | 카드·운영자·요금·이용자 유형 코드 |
| `ColumnDefinition_20250320.xlsx` | 원천 컬럼 정의와 매핑 근거 |

처리 순서는 압축 내부 파일 목록 확인, 파일 유형 판별, 인코딩·구분자 감지, canonical mapping 제안, 사용자 확인, 필수값·좌표·중복·시간 검증, 저장이다. 매핑이 미확정이거나 품질 상태가 `failed`이면 분석 실행을 차단한다.

## 8. API Contract

```text
POST   /datasets/uploads/common
POST   /datasets/uploads/daily
GET    /datasets
GET    /datasets/{dataset_id}
GET    /datasets/{dataset_id}/validation
POST   /datasets/{dataset_id}/mapping
GET    /networks/{network_version}/geojson
GET    /routes/{route_id}
GET    /routes/{route_id}/stops

POST   /scenarios
GET    /scenarios
GET    /scenarios/{scenario_id}
PATCH  /scenarios/{scenario_id}
POST   /scenarios/{scenario_id}/run
GET    /scenarios/{scenario_id}/status
```

업로드 응답은 `dataset_id`, `source_type`, 내부 파일 목록, `quality_status`, `mapping_status`를 포함한다. 시나리오 변경은 `REMOVE_STOP`, `ADD_STOP`, `REORDER_STOP`, `CHANGE_HEADWAY`, `CHANGE_SERVICE_WINDOW` 명령 목록으로 전송한다. 모든 오류 응답은 기존 계약과 동일하게 `error_code`, `message`, `details`, 관련 ID를 포함한다.

## 9. Acceptance Criteria

1. `COMMONCD.zip`을 업로드하면 내부 파일 목록과 파일 유형이 표시된다.
2. 일자별 압축파일 2개 이상을 등록하면 각 파일의 service date와 hash가 저장된다.
3. `ROUTE`, `ROUTESTTN`, `STTN`, `DWTCD`가 canonical 필드로 매핑된다.
4. 매핑 미확정, 필수 필드 누락, 좌표 오류, 중복 파일은 분석을 차단하고 구조화된 오류를 표시한다.
5. 검증 통과한 실제 지역 데이터의 노선과 정류장이 지도에 표시된다.
6. 사용자는 기존 노선 1개에 대해 정류장 추가·삭제·순서 변경 중 하나 이상을 저장할 수 있다.
7. 사용자는 배차간격 또는 운행시간대 변경을 저장할 수 있다.
8. 기준 네트워크와 기존 완료 시나리오는 편집·실행으로 변경되지 않는다.
9. 시나리오 상태가 `pending/running/completed/failed`로 조회된다.
10. 완료 시나리오의 노선별 Base 값, Scenario 값, delta가 화면에 표시된다.
11. `data/sample/common/COMMONCD.zip`과 일별 샘플을 사용해 업로드부터 결과 비교까지 재현된다.
12. 동일 입력과 설정을 재실행하면 동일한 결과 snapshot이 생성된다.
13. 전체 테스트가 Windows 저장소 내부 임시 경로에서 실행된다.
14. 기존 CLI와 기존 조회 API의 테스트가 통과한다.

## 10. Testing Plan

| 계층 | 대상 | 예상 추가 |
|---|---|---:|
| Unit | ZIP/DAT 파서, date/hash 추출 | +8 |
| Unit | 지역 파일 mapping과 검증 | +10 |
| Unit | 노선 변경과 기준 네트워크 불변성 | +6 |
| Integration | 업로드 → dataset_files/mapping 저장 | +4 |
| Integration | 실제 지역 샘플 route/stop 수요 | +3 |
| Integration | scenario draft → run → metrics | +3 |
| API | 업로드·매핑·노선·시나리오 계약 | +8 |
| Frontend | 업로드·품질·지도·노선 편집 | +6 |
| E2E | 실제 지역 1개 노선 조정 전체 흐름 | +1 |
| Environment | 저장소 내부 pytest temp 경로 | +1 |

## 11. Execution Plan

### Phase 0. 테스트 환경 안정화

pytest 임시 경로를 저장소 내부 `.test-tmp/`로 고정하고 전체 테스트를 실행한다. 후속 변경의 검증 기반이므로 선행한다.

### Phase 1. 지역 데이터 adapter 및 업로드 API

압축 내부 파일 식별, DAT 파싱, XLSX 컬럼 정의 참조, 여러 service date, hash 중복 방지와 DB 저장을 구현한다.

### Phase 2. 업로드·매핑·품질 UI

업로드 진행, 내부 파일 목록, mapping 확인, 검증 오류와 분석 가능 여부를 화면에 제공한다.

### Phase 3. 현황 지도

노선·정류장 GeoJSON API와 MapLibre 화면을 추가한다. 선택한 노선의 정류장 순서와 수요를 표시한다.

### Phase 4. 기존 노선 편집 및 시나리오

정류장·배차·운행시간 변경을 draft 명령으로 저장하고 기준 네트워크 불변성을 검증한다.

### Phase 5. 실제 지역 end-to-end

공통 압축파일과 일별 압축파일을 사용해 최소 1개 노선을 조정하고 결과 비교를 완료한다. 여러 일별 파일 등록도 확인한다.

Dependency graph:

```text
#1 테스트 환경
      ↓
#2 지역 adapter/API
      ↓
#3 업로드·품질 UI
      ↓
#4 현황 지도
      ↓
#5 노선 편집·시나리오
      ↓
#6 실제 지역 검증
```

## 12. Rollback Plan

- 업로드 실패: 해당 데이터셋만 `failed`로 보존하고 기존 데이터셋은 유지한다.
- 매핑 실패: `pending` 상태로 두고 분석 실행을 차단한다.
- 편집 취소: draft만 폐기하고 기준 네트워크는 유지한다.
- 실행 실패: `scenario_runs.status=failed`와 오류를 저장하고 기존 결과를 유지한다.
- 잘못된 결과: 해당 run만 무효화하고 새 run으로 재실행한다.
- 스키마 변경 실패: 마이그레이션 전 SQLite 백업을 만들고 애플리케이션 버전을 되돌린다.
- 원본 삭제는 2차에서 제공하지 않는다. 데이터 계보를 위해 비활성화 방식으로 처리한다.

## 13. Definition of Done

1. 실제 지역 압축파일을 웹에서 등록할 수 있다.
2. 여러 일별 파일과 hash/date를 확인할 수 있다.
3. 품질 오류와 매핑 미완료 상태가 표시된다.
4. 지도에서 노선과 정류장을 확인할 수 있다.
5. 기존 노선 1개를 편집해 시나리오를 저장할 수 있다.
6. 실행 결과와 Base/Scenario 차이를 확인할 수 있다.
7. 원천 데이터와 기준 네트워크가 변경되지 않는다.
8. Windows 전체 테스트가 통과한다.
9. 동일 입력·설정의 결과가 재현된다.

## 14. Effort Estimate

- 테스트 환경: 0.5~1일
- 지역 adapter·압축 파서·DB: 3~5일
- 업로드·매핑·품질 API: 2~3일
- React/MapLibre UI: 3~5일
- 지도 현황·노선 편집: 3~5일
- 시나리오·비교 UI: 2~3일
- 실제 지역 검증: 2~4일

총 예상: human 15~26일. OTP·OSRM 연동은 제외한다.

## 15. Files Reference

| 파일 | 변경 |
|---|---|
| `src/transit/ingest.py` | ZIP/DAT 입력과 지역 adapter |
| `src/transit/db.py` | 업로드 파일·매핑·scenario run 테이블 |
| `src/transit/api/app.py` | 업로드·매핑·지도·시나리오 API |
| `src/transit/pipeline.py` | 지역 데이터 실행 연결 |
| `src/transit/scenarios.py` | 웹 편집 명령과 불변성 검증 |
| `src/transit/metrics.py` | 지도·비교 결과 형식 |
| `src/transit/api/server.py` | 운영 DB 설정 |
| `frontend/` | 신규 React/TypeScript/MapLibre 앱 |
| `tests/` | adapter, API, UI, E2E 테스트 |
| `README.md` | 웹 실행 및 실제 지역 흐름 |

## 16. Out of Scope

- 신규 노선 생성
- 철도·OTP·OSRM 멀티모달 분석
- PostGIS·대용량 처리 전환
- 인증·권한
- 클라우드 배포
- 고급 수요 calibration 및 자동 최적화

## 17. Related

- `docs/specs/transit-mvp-spec.md`
- `docs/PRD_transit_analysis_bus_scenario.md`
- `data/sample/common/COMMONCD.zip`
- `data/sample/daily/DATA_20240420.zip`
