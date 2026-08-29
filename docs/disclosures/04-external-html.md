# 04 공시원문 외부 저장

## 목적

선택한 공시의 KIND 외부 HTML을 연도별로 저장하고, 문서 선택에 필요한 정보를 JSON 파일 하나로 압축한다.

## 단계 계약

공통 실행·재사용 규칙은 [공시 처리 공통 계약](common.md)을 따른다. 아래에는 04단계의 추가 조건만 적는다.

### 외부 HTML 다운로드

선택한 mode의 필터 결과에 기록된 공시만 내려받아 문서 선택 정보와 원본 식별값을 보존한다. 외부 HTML은 문서 선택 화면이며 실제 본문 HTML은 05단계에서 별도로 받는다.

프록시에서 저장하지 못한 대상은 같은 실행의 직접 연결로 넘겨 다시 받는다.

#### 제약과 분기

- 다운로드 대상은 `data_root`와 `mode`로만 정한다.
- `<YYYY>`는 필터 결과의 `disclosures[].disclosed_at` 연도에서 정한다. 호환 field나 중첩된 값을 탐색하지 않으며 `acpt_no`에서 연도를 추론하지 않는다.
- 서버 응답은 기존 파일 옆의 고유한 임시 파일에 먼저 저장하고 공통 HTML 구조 규칙으로 검사한다. 통과한 응답만 기존 HTML과 원자적으로 교체하며, 실패하면 임시 파일만 지우고 기존 HTML과 manifest를 유지한다.
- 직접 연결 재시도는 처음부터 직접 연결에 배정된 대상에는 적용하지 않으며, 같은 실행에서 직접 연결이 사용한 요청 간격과 분당 요청 이력을 이어받는다.

#### 중단 조건

- 필터 입력을 읽을 수 없거나 대상이 없으면 실패 처리한다.
- 취소되지 않은 실행에서 대상 HTML이 하나라도 누락되면 새 manifest를 게시하지 않는다.

### 상위 필터의 외부 HTML 재사용

파생 필터는 상위 기본 필터의 외부 HTML, manifest와 `compressed-external-html.json`을 사용한다. 압축 실행은 자기 멤버십과 원문 hash/size만 검증한다.

#### 중단 조건

- 파생 필터의 `acpt_no`가 상위 `filtered.json`, manifest나 `compressed-external-html.json`에 없거나 해시 검증을 통과하지 못하면 재사용을 중단한다.

### 실패한 외부 HTML 다시 다운로드

실패한 공시만 기본 5회까지 다시 요청한다.

#### 제약과 분기

- 재시도 뒤에도 실패한 `acpt_no`는 최종 누락 목록에 남긴다.

### 기존 외부 HTML 재사용

#### 제약과 분기

- `기존 데이터 검토`를 실행하면 선택 필터와 무관하게 모든 기본·파생 모드의 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다. 어느 모드든 미저장·손상·해시 불일치·기준 없음이 있으면 전체 판정은 `사용 불가`다.
- `외부 HTML 압축`에서도 `기존 데이터 검토`를 첫 카드로 표시한다. 저장·압축 세부 페이지 모두 선택 필터와 무관하게 모든 모드를 검사하고 한 검사 카드에 모드별 결과를 출력한다.
- 압축 파일 검사는 모드별 JSON 형식, 실제로 저장된 원문 HTML의 누락·추가·중복과 각 record의 원문 hash·size를 현재 압축 로직으로 다시 계산한 결과와 대조해 모두 출력한다. 필터 대상 중 아직 저장되지 않은 원문은 외부 저장 검사의 범위이며 압축 오류로 취급하지 않는다. 파일이 없거나 내용이 다르면 `사용 불가`로 표시한다.
- 저장된 원문 HTML이 하나도 없는 모드는 `압축 안 함`으로 통과시키며 압축 파일을 검사하거나 생성하지 않는다. 원본 유무가 혼재하면 원본이 있는 실패 모드만 `재생성`하고, 원본이 없는 모드는 그대로 건너뛴다.
- 저장·압축 검사는 아직 없는 stage 디렉터리를 만들지 않는다. 압축 재생성은 설정한 진행 확인 간격과 취소 상태를 현재 압축 작업에도 전달하며, 취소하면 현재 임시 결과를 게시하지 않고 남은 모드도 시작하지 않는다.
- 하나라도 불일치하면 기존 검사 행의 `재생성`으로 실패 결과가 가리키는 기본 모드 압축 파일만 다시 만든다. 파생 모드 실패는 그 상위 모드 파일만 재생성한다.
- 재생성 직후 서버가 모든 모드를 다시 검사하며, 화면은 검사 결과를 지우지 않고 같은 검사 행에 최종 결과를 표시한다.
- 파생 모드는 상위 모드가 소유한 동일한 원문 HTML과 압축 파일을 검사한다. 같은 압축 파일이 실패해도 상위 기본 모드 한 건만 `재생성` 대상으로 집계한다.
- 검사 상태와 결과가 달라져도 압축 검토 카드와 검사 행의 개수는 바뀌지 않는다.
- 세부 페이지를 바꾸면 이전 세부 페이지의 검사 결과를 지우고 새 검사 전 상태로 돌아간다.
- 기존 원문 무결성과 미저장 원문 수는 같은 검사 요청에서 계산하고 한 검사 행에 함께 표시한다.
- 상단 `정상`은 모든 모드의 외부 HTML 저장 검사가 통과하고 미저장 원문이 없을 때만 붙는다. 하나라도 미저장 원문이 있으면 상단은 `사용 불가`다.
- `외부 HTML 저장`에서는 `기존 원문 데이터 검사`와 `미저장 원문 다운로드`를 별도 행으로 나누지 않는다. 다운로드 필요 수는 파생 모드를 중복 합산하지 않고 원문 폴더를 실제 소유하는 기본 모드만 합산한다. 미저장·해시 불일치·기준 없음이 있으면 기존 검사 행의 `검사하기`가 `재다운로드`로 바뀌며, 문제가 있는 기본 모드의 누락·손상·해시 불일치·기준 없음 파일만 다시 받고 검증된 파일은 건너뛴 뒤 모든 모드를 다시 검사한다.

### 외부 HTML 압축 결과 생성

문서 선택 결과를 재현하는 정보만 압축 record에 저장하고 원본 화면은 복사하지 않는다.

#### 제약과 분기

- 표준 작업은 `data_root`와 `mode`에서 `04-external-html-download/<mode>` 입력과 `04-external-html-compress/<mode>` 출력을 정한다. 출력 폴더가 없으면 저장할 때 만들며, 입력 폴더에 압축 JSON을 대신 저장하지 않는다. worker 수는 `parallel_workers`로만 받는다.
- 첫 option이 선택되지 않은 정식 `본문선택` 또는 `첨부문서선택` 안내 option이면 빈 값과 빈 문서 번호를 허용하고 압축 record의 `docs`에서는 제외한다. 그 밖의 빈 option 값·문서 번호와 선택한 본문 문서 번호 누락은 실패 처리한다.
- 첨부문서가 없는 공시는 `첨부문서선택` 안내 option만 있어도 허용한다.
- 제목은 01단계 KIND 조건검색에서 받은 값만 쓰고 외부 HTML의 `<title>`이나 머리글로 보완하지 않는다.
- 외부 HTML 저장과 압축은 차례로 실행한다. 외부 HTML 저장이 실패하면 압축을 시작하지 않는다.

#### 중단 조건

- 외부 HTML 안에 `acptNo`, `mainDoc`, `attachedDoc` 또는 각 select의 option 목록이 없으면 실패 처리한다.
- 외부 HTML에서 읽은 `acptNo`가 파일명과 다르면 실패 처리하며, 빈 `acptNo`를 파일명으로 대신하지 않는다.
- 외부 HTML의 `<YYYY>` 폴더와 manifest metadata의 `disclosed_at` 연도가 다르면 실패 처리한다.

### 외부 HTML 압축 결과 검증

요청한 HTML, worker 결과와 저장한 압축 JSON의 `acpt_no` 집합이 같은지 확인한다. 압축 JSON을 저장한 뒤 파일, JSON 객체와 `records` 목록을 다시 읽어 검증한다.

#### 중단 조건

- worker 결과나 저장한 JSON에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.

### 별도 출력 경로 사용

표준 작업공간 밖에 외부 HTML과 압축 JSON을 저장할 수 있도록 각각의 입력·출력 경로를 받는다.

### 외부 HTML 결과 표시

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.

#### 제약과 분기

- 회사명이나 종목 코드를 읽지 못하면 빈 값으로 둔다.
- 본문 문서 번호나 제출일을 읽지 못해도 다른 값으로 대신하지 않는다.
- 우측 `설정`의 `진행 확인 간격 (건)`은 외부 HTML 저장과 압축 진행 로그에 함께 적용한다.

## 파일과 저장 형식

- `<data_root>/03-filter/<mode>/filtered.json`을 입력으로 받아 `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`에 외부 HTML을, `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를, `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`에 압축한 문서 선택 정보를 저장한다.
- 압축 단계는 `data_root`와 `mode`에서 입력·출력 경로를 정하며, `<data_root>/04-external-html-compress/<mode>`가 없으면 저장할 때 생성한다.
- 파생 필터 `<parent_mode>/<mode>`는 `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filtered.json`의 멤버십을 사용하되 원본은 `<data_root>/04-external-html-download/<parent_mode>`, 압축 결과는 `<data_root>/04-external-html-compress/<parent_mode>`에서 읽는다. 두 폴더 모두 `subfilters/<mode>`나 자식 `mode`의 별도 출력 폴더는 만들지 않는다.

### `<data_root>/03-filter/<mode>/filtered.json`

- 입력 형식은 [03단계](03-filter.md)의 `filtered.json` 계약을 따른다.

### `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`

- 문서 선택 정보가 있는 KIND 외부 화면을 원본 구조로 보존한 출력 파일이다.

### `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`

- [공통 HTML manifest 계약](common.md#html-manifest)을 따른다.

### `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`

- 공시·문서 식별값, 선택한 본문 문서 번호와 필터 출처를 압축해 담은 출력 파일이다.
- `records[].selected_main_doc_no`에 선택한 본문 문서 번호를 기록한다.
- `records[].metadata`에는 입력 공시 metadata를 보존하며 `records[].metadata.disclosed_at`은 입력 항목의 `disclosed_at`과 같다.
- 각 record에도 외부 HTML의 `source_size_bytes`와 `source_sha256`을 기록한다.
- 파생 필터 작업은 상위 기본 필터 파일의 `records` 중 자식 `filtered.json`의 `acpt_no` 부분집합만 검증해 사용한다.
