# 본문 HTML 저장 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 자료 흐름

- 입력 경로는 `<data_root>/04-external-html-download/<mode>`, 저장 경로는 `<data_root>/05-internal-html-download/<mode>`이며 저장 형식은 아래와 같다.
- 연도별 외부 HTML이나 `compressed-external-html.json`을 읽더라도 결과 HTML은 연도별로 저장한다.

```text
<data_root>/
├── 04-external-html-download/
│   └── <mode>/
│       ├── <year>/<acpt_no>.html
│       └── compressed-external-html.json
└── 05-internal-html-download/
    └── <mode>/
        ├── <year>/<acpt_no>.html
        └── kind_disclosure_html_manifest.json
```

## 처리 계약

### 정상 동작

#### 본문 문서 번호 기준

04단계가 확정한 본문 문서 번호를 그대로 다운로드 대상에 사용한다.
- 압축 JSON을 입력할 때는 `records[].selected_main_doc_no`만 본문 문서 번호 SoT로 사용한다.
- 연도별 외부 HTML을 직접 입력할 때도 `mainDoc`에서 직접 고른 문서 번호만 사용한다.

#### 내부 HTML 저장

선택한 공시에서 받은 KIND 본문 HTML을 원본 식별값과 함께 보존한다.
- 본문은 선택한 mode, 공시 연도와 접수번호를 사용해 `<mode>/<year>/<acpt_no>.html`로 저장한다.

#### 다운로드 대상 무결성 검사

요청 대상과 저장 결과에 같은 접수번호 집합이 들어 있는지 확인한다.
- 일반 실행에서는 중복·누락·추가 접수번호가 없는지 확인한다.
- 사용자가 작업을 취소하면 그 뒤 생긴 누락은 허용하되, 저장 항목이 중복되거나 추가됐는지는 계속 검사한다.

#### 내부 HTML manifest metadata 연결

검증을 마친 내부 HTML이 요청한 원본 공시와 연결됐음을 manifest에 기록한다.
- 다운로드 대상 무결성 검사를 통과한 HTML은 `acpt_no`를 원본 metadata와 연결해 `kind_disclosure_html_manifest.json`에 기록한다.
- 파일마다 바이트 수를 `source_size_bytes`, SHA-256을 `source_sha256`에 기록한다.
- manifest는 저장 HTML을 건드리지 않고 원본 연결과 완료 결과를 증명한다.

## 화면과 서비스 계약

### 정상 동작

#### 내부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
