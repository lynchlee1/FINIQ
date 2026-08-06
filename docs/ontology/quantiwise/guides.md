# Quantiwise

## 목적

Excel 자료를 미리 보고 Parquet으로 바꾸거나 합친다.

## 핵심 기능

### Excel 미리보기와 변환

Excel 시트와 계정 mapping을 읽어 종목·날짜·계정별 Parquet을 만든다.

### Parquet 병합

여러 입력의 날짜·종목·계정 값을 하나의 결과로 합친다.

### 중복 Parquet 정리

같은 계정의 포함 관계와 값 일치를 비교해 남길 파일을 정한다.

### 통합 자료 생성

Quantiwise 입력과 시장 이력을 DataFrame index와 날짜 기준으로 합친다.

### 변환 결과 표시

backend가 반환한 출력 파일과 계정·날짜·회사 hash를 화면에 표시한다.
