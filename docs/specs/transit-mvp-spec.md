# Transit MVP 실행계획 및 기술 Spec

- 문서 상태: 승인된 MVP 기준안
- 작성일: 2026-08-31
- 기준 문서: `docs/PRD_transit_analysis_bus_scenario.md`
- 목적: 개발 착수

## 1. 목적과 사용자

Transit은 교통카드와 BIS 파일을 입력받아 대중교통 현황을 분석하고, 단일 버스 노선의 신규 생성 또는 조정에 따른 수요·서비스·운영 지표를 비교하는 플랫폼이다.

Primary Persona는 교통계획·교통연구 실무자이며, Secondary Persona는 지자체·지역 버스 담당자다. 전자는 실제 수요와 가정을 검증해야 하고, 후자는 복잡한 교통모형을 직접 구성하지 않고 노선 변경 효과를 확인해야 한다.

현재 저장소에는 구현 코드 없이 `README.md`와 `docs/PRD_transit_analysis_bus_scenario.md`만 있다. 따라서 이 문서는 기존 기능 수정이 아닌 greenfield 시스템 구축을 위한 기준이다.

## 2. MVP 범위

### 포함

1. CSV/Parquet 교통카드·BIS 파일 등록
2. 컬럼 자동 추정과 사용자 확인형 표준 매핑
3. 결측·중복·좌표·식별자 품질검사
4. SQLite 기반 데이터셋·노선·정류장·거래·시나리오 저장
5. 관측 승차·하차 집계
6. `OBSERVED`·`INFERRED`·`UNKNOWN` 하차 상태 분리
7. 신규 버스 노선 생성
8. 기존 단일 노선의 정류장·순서·경로·배차간격·운행시간대 조정
9. Python 기반 거리·통행시간·generalized cost·Logit 계산
10. 기준안과 변경안의 KPI 비교
11. CSV 및 GeoJSON export
12. 노선 2개 이상, 정류장 20개 이상, 거래 200건 이상의 합성 샘플 데이터
13. CLI 기반 전체 실행 흐름과 자동화 테스트

### 제외

- OTP, OSRM, PostgreSQL/PostGIS
- 철도·도시철도 분석
- 외부 API 자동 수집 및 실시간 BIS/GTFS-Realtime
- 지역별 자동 Calibration
- 신규 수요 유발·장기 수요예측
- 전체 버스망 자동 최적화
- 차량 스케줄링·운전자 근무표·차고지 최적화
- 인증·다중 사용자 권한
- 클라우드 배포·운영 모니터링

## 3. 성공 기준

합성 샘플 데이터셋으로 다음 흐름을 재현한다.

```text
데이터 등록 → 품질검사 → 표준화 → 현황 집계
→ 신규 또는 조정 노선 시나리오 생성
→ 기존 수요 재배정 → KPI 비교
→ CSV·GeoJSON export
```

완료 시 샘플 데이터 1개를 처음부터 끝까지 처리하고, 관측값과 추정값을 구분하며, 기준 네트워크를 보존한 채 노선 변경 전후의 노선·정류장·OD·운영 KPI를 비교할 수 있어야 한다.

## 4. 기술 아키텍처

```text
CSV/Parquet
    ↓
Reader + Column Mapping + Validator
    ↓
Canonical Model + SQLite
    ↓
Observed Demand / Journey Builder
    ↓
Scenario Builder
    ↓
Cost Calculator + Logit Assignment
    ↓
Metrics + CSV/GeoJSON Export
```

| 영역 | MVP 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.11 이상 | 데이터 처리와 분석 로직 통일 |
| 저장소 | SQLite | 별도 서버 없이 재현 가능한 단일 파일 |
| 입력 | CSV, Parquet | 지역별 원천 파일 수용 |
| 공간 결과 | GeoJSON | 지도 도구와의 호환성 |
| 실행 | CLI 우선 | 웹 UI 없이 핵심 파이프라인 검증 |
| 웹 계층 | 후속 adapter | 도메인 로직과 API 분리 |

## 5. 프로젝트 구조

```text
Transit/
├─ README.md
├─ pyproject.toml
├─ src/transit/
│  ├─ cli.py
│  ├─ config.py
│  ├─ db.py
│  ├─ models.py
│  ├─ ingest/{reader.py,mapping.py,validator.py}
│  ├─ network/{stops.py,routes.py,geometry.py,travel_time.py}
│  ├─ demand/{transactions.py,journeys.py,alighting.py,cost.py,logit.py}
│  ├─ scenarios/{schema.py,builder.py,assignment.py}
│  └─ metrics/{observed.py,comparison.py,export.py}
├─ tests/{fixtures,unit,integration,e2e}/
├─ data/sample/
└─ docs/specs/transit-mvp-spec.md
```

## 6. SQLite 데이터 모델

DB 파일은 `data/transit.sqlite3`, 원천 파일은 `data/raw/<dataset_id>/`에 저장한다. 원천 파일은 수정하지 않는다.

```sql
CREATE TABLE datasets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('CARD', 'BIS', 'MANUAL')),
  file_path TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('pending', 'passed', 'failed')),
  created_at TEXT NOT NULL
);

CREATE TABLE stops (
  id TEXT PRIMARY KEY,
  source_dataset_id TEXT NOT NULL,
  source_stop_id TEXT NOT NULL,
  name TEXT NOT NULL,
  latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  canonical_status TEXT NOT NULL,
  FOREIGN KEY (source_dataset_id) REFERENCES datasets(id)
);

CREATE TABLE routes (
  id TEXT PRIMARY KEY,
  source_dataset_id TEXT NOT NULL,
  source_route_id TEXT NOT NULL,
  name TEXT NOT NULL,
  direction TEXT,
  canonical_status TEXT NOT NULL,
  FOREIGN KEY (source_dataset_id) REFERENCES datasets(id)
);

CREATE TABLE route_stops (
  route_id TEXT NOT NULL,
  stop_id TEXT NOT NULL,
  stop_sequence INTEGER NOT NULL CHECK (stop_sequence > 0),
  distance_m REAL,
  travel_time_s REAL,
  source_type TEXT NOT NULL,
  PRIMARY KEY (route_id, stop_sequence),
  FOREIGN KEY (route_id) REFERENCES routes(id),
  FOREIGN KEY (stop_id) REFERENCES stops(id)
);

CREATE TABLE card_transactions (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  transaction_time TEXT NOT NULL,
  journey_key TEXT,
  route_id TEXT,
  boarding_stop_id TEXT,
  alighting_stop_id TEXT,
  transfer_group_id TEXT,
  transaction_type TEXT NOT NULL,
  alighting_status TEXT NOT NULL,
  FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);

CREATE TABLE journeys (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  boarding_time TEXT NOT NULL,
  origin_stop_id TEXT NOT NULL,
  destination_stop_id TEXT,
  destination_status TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);

CREATE TABLE scenarios (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_network_version TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE scenario_changes (
  id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  change_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
);

CREATE TABLE metric_results (
  id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  base_value REAL,
  scenario_value REAL,
  delta_value REAL,
  created_at TEXT NOT NULL
);
```

모든 파생 결과에는 `source_dataset_id`, `derivation_method`, `quality_status`, `confidence_score`, `version`을 기록한다. `ambiguous`, `unmatched`, `invalid` 데이터는 관리자가 확정하기 전까지 자동 분석에서 제외한다.

## 7. 입력 및 품질검사

교통카드의 논리 필드는 `transaction_id`, `transaction_time`, `route_id`, `boarding_stop_id`, 선택적 `alighting_stop_id`, `card_id` 또는 익명화 `journey_key`, 선택적 `transfer_id`, `transaction_type`이다.

BIS의 논리 필드는 `route_id`, `route_name`, `direction`, `stop_id`, `stop_name`, `stop_sequence`, `latitude`, `longitude`이며 `service_start_time`, `service_end_time`, `headway_seconds`는 선택적이다.

처리 순서는 인코딩·구분자·타입 감지, 표준 필드 후보 매핑, 사용자 확인, 필수값 검사, 좌표 검사, 중복 검사, SHA-256 중복 파일 검사, 품질 리포트 생성으로 고정한다. 필수 필드 누락, 좌표 범위 초과, 중복 식별자, 음수·중복 순서, 파싱 불가 시간값은 구조화된 실패 사유로 반환한다.

## 8. 수요 처리 및 시나리오

- 실제 하차값은 `OBSERVED`로 저장한다.
- 카드·환승 연결과 노선 순서로 제한적으로 추정할 수 있을 때만 `INFERRED`로 저장한다.
- 근거가 부족한 목적지는 생성하지 않고 `UNKNOWN`으로 남긴다.
- 현황 집계는 기본적으로 `OBSERVED`만 사용한다.
- 재배정은 `OBSERVED`와 신뢰도 기준을 통과한 `INFERRED`만 사용한다.
- `UNKNOWN`은 총 승차량에는 포함하되 OD 재배정에는 포함하지 않는다.

일반화 비용과 기본 Logit은 다음과 같다.

```text
generalized_cost = in_vehicle_time + walking_time
                 + transfer_count * transfer_penalty + waiting_time
P(route_i) = exp(-beta * cost_i) / Σ exp(-beta * cost_j)
```

기본 파라미터는 설정 파일에서 관리한다.

```yaml
model:
  beta: 0.08
  transfer_penalty_seconds: 600
  walking_speed_mps: 1.2
  default_bus_speed_kph: 20
  boarding_dwell_seconds: 20
```

시나리오는 기준 네트워크를 직접 수정하지 않고 기준 버전과 변경 명령 목록으로 재현한다.

```json
{
  "change_type": "CREATE_ROUTE",
  "route_id": "R_NEW_001",
  "route_name": "신규노선 1",
  "stops": ["S001", "S005", "S009", "S014"],
  "headway_seconds": 600,
  "service_start_time": "06:00",
  "service_end_time": "23:00"
}
```

지원 변경 유형은 `CREATE_ROUTE`, `DELETE_ROUTE`, `ADD_STOP`, `REMOVE_STOP`, `REORDER_STOP`, `CHANGE_HEADWAY`, `CHANGE_SERVICE_WINDOW`이다. 실패한 실행은 `failed` 상태로 남기며 기존 데이터에 영향을 주지 않는다.

## 9. KPI와 CLI

최소 KPI는 총 승차 건수, 노선별 승차 수요, 정류장별 승하차 수요, OD별 수요, 평균 통행시간, 평균 대기시간, 평균 환승 횟수, 수요 증감, 영향 정류장 수, 서비스 커버리지, 운행횟수, 배차간격, 필요 차량 수다.

```text
required_vehicles = ceil(round_trip_time_seconds / headway_seconds)
```

CLI 계약:

```text
transit dataset register --file <path> --type card|bis
transit dataset validate --dataset <id>
transit network build --dataset <id>
transit demand summarize --dataset <id>
transit scenario create --base <network_version> --file <scenario.json>
transit scenario run --scenario <id> 또는 --file <scenario.json>
transit scenario compare --scenario <id> --format csv|geojson
```

`network build`는 BIS dataset을 기준으로 정류장 좌표가 포함된 기준 네트워크 JSON을 생성한다. `scenario create --base <network_version> --file <scenario.json>`는 재현 가능한 draft를 저장하고, 이후 `scenario run --scenario <id>`가 같은 scenario 레코드를 실행 상태에서 완료 상태로 갱신한다. 상세 KPI는 조회 API의 `/scenarios/{id}/metrics/detail`에서 scope type과 metric name을 포함해 반환한다.

실패 응답에는 `error_code`, `message`, `details`, 관련 `dataset_id` 또는 `scenario_id`를 포함한다. 동일 입력·파라미터 실행은 입력 해시 또는 idempotency key로 중복을 감지한다.

## 10. 실행계획

| 순서 | 작업 | 산출물 | 예상 effort |
|---:|---|---|---:|
| 1 | Python 패키지·SQLite migration | 기본 앱과 스키마 | 1일 |
| 2 | Reader·매핑·검증 | dataset 등록·품질 리포트 | 2일 |
| 3 | 표준화·Crosswalk | 표준 노선·정류장·거래 | 2일 |
| 4 | Journey·현황 집계 | 관측 수요 결과 | 2일 |
| 5 | 시나리오·비용·Logit | 재배정 결과 | 3일 |
| 6 | KPI·CSV/GeoJSON | export 파일 | 2일 |
| 7 | CLI·샘플·README | 재현 가능한 전체 흐름 | 2일 |
| 8 | 단위·통합·E2E·회귀 테스트 | 자동화 테스트 | 2일 |

총 예상 effort는 16 개발일이며 실제 원천 파일 복잡도에 따라 조정한다.

## 11. 테스트 계획

| 계층 | 검증 내용 | 최소 목표 |
|---|---|---:|
| Unit | 매핑, 좌표·중복 검사, Journey 분류, 거리·시간·Logit·차량 계산 | 25개 |
| Integration | 파일 등록 → SQLite 저장 → 현황 집계 | 5개 |
| Integration | 시나리오 → 재배정 → KPI → export | 5개 |
| E2E | 샘플 데이터 CLI 전체 흐름 | 1개 |
| Regression | 동일 입력 결과 해시 비교 | 2개 |

## 12. 수용 기준

1. 샘플 데이터가 노선 2개 이상, 정류장 20개 이상, 거래 200건 이상을 포함한다.
2. 유효한 CSV 또는 Parquet 등록 후 dataset ID가 반환된다.
3. 필수 컬럼 누락 파일은 `failed`와 누락 필드명을 반환한다.
4. 동일 SHA-256 파일은 중복 등록되지 않는다.
5. 유효한 BIS의 노선·정류장·순서가 SQLite에 저장된다.
6. 좌표 오류, 중복 식별자, 음수 순서, 필수값 결측이 검출된다.
7. 관측·추정·미확정 목적지가 세 상태로 구분된다.
8. 현황 승차 총계가 유효 승차 원천 건수와 일치한다.
9. 신규 노선 시나리오가 기준 네트워크와 분리된다.
10. 기존 단일 노선의 정류장 순서와 배차간격을 변경할 수 있다.
11. 시나리오 실패 시 기존 데이터가 보존된다.
12. 동일 입력·네트워크·파라미터 재실행 결과가 동일하다.
13. 노선·정류장·OD·네트워크 KPI에 base·scenario·delta가 생성된다.
14. 배차간격과 왕복시간으로 필요 차량 수가 계산된다.
15. 결과를 CSV와 유효한 GeoJSON FeatureCollection으로 export할 수 있다.
16. 오류 응답에 구조화된 오류 코드가 포함된다.
17. 단위·통합·E2E 테스트가 통과한다.
18. MVP 실행에 OTP·OSRM·PostgreSQL·PostGIS·외부 API가 필요하지 않다.
19. README에 설치·샘플·시나리오·export 절차가 문서화된다.

## 13. 롤백과 후속 확장

원천 파일은 수정하지 않는다. dataset·network·scenario·model parameter에 버전을 부여하고 잘못된 파생 결과는 비활성화한 뒤 이전 버전을 선택한다. SQLite 스키마는 migration으로 관리하고, 문제 발생 시 마지막 정상 SQLite snapshot과 애플리케이션 커밋으로 복구한다.

후속 OTP·OSRM·PostGIS 도입은 `NetworkRouter`와 `SpatialStore` adapter로 분리한다. 철도망 결합, 자동 Calibration, 웹 UI, 인증, 실시간 연동은 별도 spec으로 작성한다.
