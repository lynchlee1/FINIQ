# Quantiwise 검증과 중단

아래 경로는 `src/` 기준이다.

## 통합문서 읽기

- **finiq/data/assets\_excel.py**
- **통합문서를 `calamine`으로 읽을 수 없음**
  - 읽기 요청을 오류로 처리한다.

## 병합 입력과 충돌

- **finiq/data/assets\_excel.py**
- **병합 입력 Parquet 하나에 `date` 열이 없음**
  - 병합 전체를 오류로 처리하며 병합 결과를 남기지 않는다.
- **병합 입력들이 같은 날짜·종목·계정 칸에 서로 다른 실제 값을 가짐**
  - 두 입력값이 같으면 그 값을 유지하고 충돌로 처리하지 않는다. 값이 다르면 병합 전체를 오류로 처리하고 결과를 남기거나 값 하나를 임의로 고르지 않는다.
- **통합 Parquet 병합 요청에서 `input_directories`가 비어 있거나 배열이 아님**
  - 이전 `input_directory` 이름으로 대체하지 않고 요청을 오류로 처리한다.

## preview 입력

- **finiq/data/assets\_excel.py**
- **단일 Excel preview에서 필수 필드 값을 찾지 못함**
  - preview 요청을 오류로 처리한다.
- **단일 Excel preview에 값이 있는 잘못된 날짜가 있음**
  - 행을 제외해 정상처럼 보이는 일부 preview를 만들지 않고 요청을 오류로 처리한다.

## 결과 교체

- **finiq/data/assets\_excel.py**
- **Parquet 결과 교체나 병합 입력 이동 중 오류가 발생함**
  - 이번 실행에서 새로 올린 결과를 제거하고 기존 결과와 이미 옮긴 입력을 원래 위치로 복원한 뒤 오류로 처리한다.

## 중복 정리

- **finiq/data/assets\_parquet\_cleanup.py**
- **다음 중 하나에 해당하면 중복 정리 요청 전체를 오류로 처리함**
  - Parquet footer, 계정 metadata, 표 본문 가운데 하나가 없음
  - 날짜를 읽거나 변환할 수 없음
  - footer의 `account_name`이 비어 있음
  - 정리 실행 전에 삭제 후보 파일이 없어짐

## 통합 결과와 시장 이력

- **finiq/market\_desk/analytics/quanti\_integrated.py**
- **통합문서나 시트를 읽을 수 없거나 비어 있음**
  - 오류로 처리한다.
- **입력 폴더·`date` 열이 없거나 병합할 항목 자료가 비어 있음**
  - 오류로 처리한다.

- **finiq/market\_desk/analytics/quanti\_market\_history.py**
- **대응표에서 찾을 수 없는 시장값이 하나라도 있음**
  - 오류로 처리한다.

## 표시 한계

- backend 검증 오류에는 잘못된 날짜와 중복 종목 코드·날짜를 앞에서 5개까지만 넣는다. 병합 표에서 종목 코드가 빠진 오류는 앞에서 3개까지만 넣는다. 검증과 실패 판단에는 전체 값을 사용한다.
- 시장 대응표에 없는 값을 알리는 오류 문장은 앞 10개 열에서 열마다 값 5개까지만 보여 준다. 검증과 실패 판단에는 전체 값을 사용한다.
