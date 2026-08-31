# Transit

교통카드 데이터를 기반으로 대중교통 현황을 분석하고, 버스 노선의 신규 생성·조정에 따른 수요 변화를 시나리오별로 예측하는 교통 데이터 분석 플랫폼입니다.

## 프로젝트 소개

대중교통 노선을 신설하거나 변경할 때는 기존 이용 패턴, 시간대별 수요, 정류장 간 이동 흐름, 환승 수요 등 다양한 데이터를 함께 검토해야 합니다. Transit은 교통카드 데이터를 입력받아 현재 교통 수요를 시각화하고, 노선 변경안에 따른 이용객 변화를 비교·분석할 수 있도록 지원합니다.

이를 통해 교통 정책 담당자와 버스 운영자는 데이터에 기반해 노선 운영 의사결정을 내리고, 변경 전후의 효과를 사전에 검토할 수 있습니다.

## 주요 사용자

- 지자체 및 교통 정책 담당자
- 버스·대중교통 운영기관
- 교통 수요 및 도시계획 분석가
- 노선 개편 및 운영 효율화를 담당하는 실무자

## 핵심 기능

### 1. 교통카드 데이터 입력

- 교통카드 승·하차 데이터를 업로드하거나 연동
- 이용 일시, 승·하차 정류장, 노선, 이용자 유형 등 주요 항목 관리
- 분석 기준일, 시간대, 지역, 노선별 데이터 필터링
- 데이터 형식 및 누락·오류 검증

### 2. 대중교통 현황 분석

- 시간대·요일별 승하차 수요 분석
- 정류장 및 노선별 이용량 비교
- 승객 이동 흐름과 주요 통행 구간 분석
- 환승 수요 및 혼잡 구간 파악
- 지도와 차트를 활용한 분석 결과 시각화

### 3. 버스 노선 신규 생성 및 조정

- 신규 버스 노선 생성
- 기존 노선의 정류장, 운행 구간, 배차 조건 조정
- 노선별 운행 범위와 영향 지역 확인
- 변경 전·후 노선 비교
- 노선 변경안 저장 및 시나리오별 관리

### 4. 수요 변화 시나리오 예측

- 신규 노선 개통에 따른 예상 이용 수요 분석
- 정류장 추가·삭제 및 노선 우회에 따른 승객 변화 예측
- 배차 간격, 운행 시간, 환승 조건 변경 시나리오 비교
- 기존 노선과 신규·조정 노선 간 수요 이동 분석
- 시나리오별 예상 승객 수, 혼잡도, 커버리지 비교

### 5. 분석 결과 리포트

- 현황 분석 및 시나리오 결과 요약
- 주요 지표와 변동 폭 비교
- 노선별·지역별 영향 확인
- 의사결정에 활용할 수 있는 결과 저장 및 공유

## 데이터 흐름

```text
교통카드 데이터 입력
        ↓
데이터 검증 및 전처리
        ↓
현황 분석 및 수요 패턴 추출
        ↓
노선 신규 생성·조정
        ↓
시나리오별 수요 변화 예측
        ↓
결과 비교·시각화·리포트
```

## 주요 분석 지표 예시

| 분류 | 지표 |
| --- | --- |
| 이용 수요 | 승차 건수, 하차 건수, 시간대별 이용량 |
| 노선 운영 | 노선별 이용량, 정류장별 이용량, 운행 구간 |
| 이동 흐름 | 주요 출발·도착 구간, 통행량, 환승 수요 |
| 서비스 영향 | 수요 증가·감소량, 영향 정류장 수, 대중교통 커버리지 |
| 운영 효율 | 혼잡 변화, 노선 간 수요 이동, 예상 운송 수요 |

## 활용 시나리오

### 출퇴근 수요가 높은 지역에 신규 노선 도입

교통카드 데이터를 통해 출퇴근 시간대의 이동량과 주요 통행 구간을 확인하고, 신규 노선 도입 시 예상 수요와 기존 노선의 수요 변화를 비교합니다.

### 특정 노선의 정류장 및 운행 구간 조정

이용량이 낮은 정류장을 조정하거나 우회 구간을 변경한 뒤, 승객 접근성·이용 수요·주변 노선에 미치는 영향을 시나리오별로 검토합니다.

### 환승 수요를 고려한 노선 개편

주요 환승 지점과 이동 흐름을 분석하여 환승 연결성을 개선하는 노선안을 만들고, 개편 전후의 예상 수요와 혼잡 변화를 확인합니다.

## 기대 효과

- 교통카드 데이터 기반의 객관적인 노선 운영 의사결정
- 노선 개편 전에 다양한 대안을 비교하고 위험 요소 검토
- 시간대·지역별 교통 수요에 맞춘 서비스 개선
- 노선 변경에 따른 승객 이동과 운영 효과의 사전 예측
- 분석 결과를 활용한 정책 설명 및 관계자 협업 지원

## 프로젝트 구조

현재 프로젝트는 플랫폼의 방향성과 기능을 정의하는 초기 단계입니다. 실제 구현이 진행되면 다음과 같은 영역으로 확장할 수 있습니다.

```text
Transit/
├─ README.md              # 프로젝트 문서
├─ data/                  # 입력 데이터 및 샘플 데이터
├─ analysis/              # 수요 분석 및 예측 로직
├─ scenarios/             # 노선 변경 시나리오
├─ backend/               # 데이터 처리 및 API
├─ frontend/              # 분석 화면 및 시각화
└─ docs/                  # 설계 및 운영 문서
```

## 향후 개발 예정

- 교통카드 데이터 업로드 및 자동 검증 기능
- 정류장·노선 기반 지도 시각화
- 노선 편집 및 시나리오 저장 기능
- 수요 예측 모델 고도화
- 시나리오 간 성과 비교 대시보드
- 분석 결과 리포트 다운로드 및 공유
- 실제 운행 데이터와 예측 결과의 사후 비교

## 기술 스택

현재 MVP는 Python 3.11 이상과 SQLite를 사용합니다. OTP, OSRM, PostgreSQL/PostGIS, 외부 API 및 실시간 데이터 연동은 후속 범위입니다.

## 로컬 실행

```bash
python -m pip install -e ".[dev,api,parquet]"
python -m pytest -q
```

샘플 교통카드와 BIS 데이터를 등록합니다.

```bash
python -m transit.cli dataset register --file data/sample/cards.csv --type card
python -m transit.cli dataset register --file data/sample/bis.csv --type bis
python -m transit.cli demand summarize --dataset <card-dataset-id>
python -m transit.cli demand summarize --dataset <card-dataset-id> --scope stop
python -m transit.cli network build --dataset <bis-dataset-id> --output network.json
python -m transit.cli scenario create --file data/sample/scenario.json
python -m transit.cli scenario run --scenario <scenario-id>
python -m transit.cli scenario run --file data/sample/scenario.json
python -m transit.cli scenario compare --scenario <scenario-id> --format csv --output metrics.csv
python -m transit.cli scenario compare --scenario <scenario-id> --format geojson --network network.json --output routes.geojson
```

기본 SQLite 파일은 `data/transit.sqlite3`에 생성됩니다. 다른 경로를 사용하려면 `--db` 옵션을 지정할 수 있습니다.

## 개발 상태

현재 구현된 MVP 기반 기능은 다음과 같습니다.

- CSV 교통카드·BIS 파일 등록 및 SQLite 저장
- 필수 필드와 좌표 범위 품질검사
- 노선별 정류장 순서·복합 중복 품질검사
- dataset 품질 오류의 SQLite 구조화 저장 및 JSON 검증 결과
- 기준 BIS 네트워크 JSON 생성 및 저장형 시나리오 실행
- 관측·추정 불가 하차 상태 분리
- 불변 버스 시나리오 변환
- 기본 Logit 경로선택 계산
- KPI 비교 및 GeoJSON export primitive

세부 구현 기준과 후속 개발 순서는 [`docs/specs/transit-mvp-spec.md`](docs/specs/transit-mvp-spec.md)를 참고하세요.

## 조회 API

FastAPI 조회 계층은 애플리케이션 코드에서 다음과 같이 생성할 수 있습니다.

```python
from transit.api.app import create_app
from transit.db import Database

app = create_app(Database("data/transit.sqlite3"))
```

제공 endpoint:

- `GET /health`
- `GET /datasets/{dataset_id}/demand`
  - `?scope=route` (기본값) 또는 `?scope=stop`
- `GET /scenarios/{scenario_id}/metrics`
- `GET /scenarios/{scenario_id}/metrics/detail` (노선·정류장·OD·네트워크 범위)

`dataset validate`는 `dataset_id`, `quality_status`, `errors[{error_code, field, message}]` 구조의 JSON을 출력합니다.

## 라이선스

라이선스는 추후 프로젝트 정책에 따라 추가할 예정입니다.
