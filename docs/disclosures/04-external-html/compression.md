# 04 압축 결과 생성

## 외부 HTML 압축 결과 생성

문서 선택 결과를 재현하는 정보만 압축 record에 저장하고 원본 화면은 복사하지 않는다.

### 입력·출력과 실행 순서

- 표준 작업은 `data_root`와 `mode`에서 `04-external-html-download/<mode>` 입력과 `04-external-html-compress/<mode>` 출력을 정한다. 출력 폴더가 없으면 저장할 때 만들며, 입력 폴더에 압축 JSON을 대신 저장하지 않는다. worker 수는 `parallel_workers`로만 받는다.
- 제목은 01단계 KIND 조건검색에서 받은 값만 쓰고 외부 HTML의 `<title>`이나 머리글로 보완하지 않는다.
- 외부 HTML 저장과 압축은 차례로 실행한다. 외부 HTML 저장이 실패하면 압축을 시작하지 않는다.

### 문서 선택

- 첫 option이 선택되지 않은 정식 `본문선택` 또는 `첨부문서선택` 안내 option이면 빈 값과 빈 문서 번호를 허용하고 압축 record의 `docs`에서는 제외한다. 그 밖의 빈 option 값·문서 번호와 선택한 본문 문서 번호 누락은 실패 처리한다.
- 첨부문서가 없는 공시는 `첨부문서선택` 안내 option만 있어도 허용한다.

### 중단 조건

- 외부 HTML 안에 `acptNo`, `mainDoc`, `attachedDoc` 또는 각 select의 option 목록이 없으면 실패 처리한다.
- 외부 HTML에서 읽은 `acptNo`가 파일명과 다르면 실패 처리하며, 빈 `acptNo`를 파일명으로 대신하지 않는다.
- 외부 HTML의 `<YYYY>` 폴더와 manifest metadata의 `disclosed_at` 연도가 다르면 실패 처리한다.

## 외부 HTML 압축 결과 검증

요청한 HTML, worker 결과와 저장한 압축 JSON의 `acpt_no` 집합이 같은지 확인한다. 압축 JSON을 저장한 뒤 파일, JSON 객체와 `records` 목록을 다시 읽어 검증한다.

### 중단 조건

- worker 결과나 저장한 JSON에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.
