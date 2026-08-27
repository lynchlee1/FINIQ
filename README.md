# FINIQ

FINIQ(피닉)는 공시 데이터를 수집하고, 기업별로 정리해, 가격 데이터와 함께 분석/시각화하는 프로젝트입니다.

FINIQ가 유일한 프로젝트 루트입니다. `finiq_*` 폴더들은 독립 프로젝트가 아니라 소스와 테스트를 나누는 내부 모듈 경계입니다.

## 컴포넌트

### finiq_dataScraper

KRX KIND 공시 데이터를 다운로드하고 파싱합니다. 검색 결과, 공시 원문, 기업별 공시 분류 산출물을 만드는 데이터 수집 컴포넌트입니다.

### finiq_structureNL

공시 원문에서 핵심 구조화 정보를 추출합니다. 전환사채 등 증권 발행 공시에서 발행일, 만기일, 전환가액 같은 필드를 파싱합니다.

### finiq_marketDesk

수집된 공시 데이터와 가격 데이터를 결합해 분석 API를 제공합니다. 기업 목록, 공시 타임라인, 차트용 데이터, 다운로드 작업을 처리합니다.

### finiq_GUI

FINIQ의 웹 화면을 담은 프론트엔드 워크스페이스입니다. MarketDesk 화면과 Graph Viewer 앱, 공통 UI/theme 패키지, 그리고 Graph Viewer core(@finiq/graph-viewer)를 포함합니다.

## UI

### MarketDesk

MarketDesk는 수집된 KIND 공시를 기업 단위로 탐색하는 분석 화면입니다. 기업 목록에서 종목을 고르고, 상세 화면에서 공시 타임라인과 주가 차트를 함께 봅니다. 공시 그룹 필터, 기간/빈도 선택, 가격 데이터 소스 선택, 기업 목록 export 같은 기능도 제공합니다.

### MarketDesk Download

Download 화면은 KIND 데이터 수집 작업을 웹에서 실행하는 UI입니다. 날짜 범위, 기업명, 제출인, 시장, 공시 유형, page size, worker 수 등을 설정해 다운로드를 preview하거나 실행할 수 있고, 진행 로그와 작업 상태를 확인합니다. 연도별 분할 다운로드와 resume 흐름도 이 화면에서 다룹니다.

### Graph Viewer

Graph Viewer는 graph JSON을 시각적으로 탐색하는 UI입니다. 노드와 엣지를 force graph로 표시하고, 검색/필터링, 선택, 숨김, 삭제, pin, 이웃 노드 보기, undo/redo, 스타일 설정, JSON/SVG/PNG export를 지원합니다.

## 기본 흐름

1. `finiq_dataScraper`가 KIND 데이터를 수집합니다.
2. `finiq_structureNL`이 필요한 공시 원문 필드를 구조화합니다.
3. `finiq_marketDesk`가 공시와 가격 데이터를 분석용 API로 제공합니다.
4. `finiq_GUI`가 분석 결과를 화면에 표시합니다.
5. `finiq_graphViewer`는 그래프 기반 탐색 기능을 제공합니다.

## 개발 명령

프런트엔드 npm 명령은 저장소의 `frontend` 디렉터리에서 실행합니다.

```bash
cd frontend
npm install
npm run build
npm run dev:graph-viewer
npm run dev:market-desk
```

MarketDesk 백엔드와 프론트엔드를 함께 실행하려면 저장소 루트에서 다음 명령을 사용합니다.

```bash
./scripts/dev-market-desk.sh
```

두 서버는 `Ctrl+C` 한 번으로 함께 종료됩니다.

Backend API는 `src/finiq/market_desk/web/app.py`에서 실행하며, 기본 포트는 `8765`입니다.
공통 설정은 `src/finiq/config.py`에서 관리됩니다.

Python 테스트도 저장소 루트에서 실행합니다.

```bash
.venv/bin/python -m pytest
```

`resources/`는 로컬 생성 데이터 위치이며 Git에 올리지 않습니다. GitHub Desktop에서는 루트 저장소의 작업 상태와 커밋 범위를 확인합니다.
