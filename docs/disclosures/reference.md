# 공시 분석 공통 Reference

### 이상적인 폴더 구조

모든 작업은 아래 구조를 따른다.

```text
<data_root>/
├── disclosure-workspace.json
├── 01-list/
│   └── <YYYYMMDD>_<YYYYMMDD>/
│       ├── *_post_page_*.body
│       ├── kind_workflow.input.json
│       └── kind_workflow.checkpoint.json
├── 02-table/
│   ├── <YYYY>.sqlite
│   └── sqlite_manifest.json
├── 03-filter/
│   ├── <workflow-name>.json
│   └── <mode>/
│       └── filtered.json
├── 04-external-html-download/
│   └── <mode>/
│       ├── <YYYY>/
│       │   └── <acpt_no>.html
│       ├── kind_disclosure_html_manifest.json
│       └── compressed-external-html.json
├── 05-internal-html-download/
│   └── <mode>/
│       ├── <YYYY>/
│       │   └── <acpt_no>.html
│       └── kind_disclosure_html_manifest.json
├── 06-sections/
│   └── <YYYY>/
│       └── <acpt_no>.html
├── 07-converted/
│   └── <mode>/
│       └── parsed-<mode>.json
└── 09-disclosure-graph/
    └── disclosure-graph.json
```

### 식별자

- KIND에는 기업 구분용 키 `company_id`와 문서 구분용 키 `acpt_no`, `doc_no`가 존재한다.
- DART에는 기업 구분용 키 `corp_code`, `stock_code`와 문서 구분용 키 `rcept_no`가 존재한다.
- 이 식별자는 모두 로마자를 포함할 수 있는 텍스트다. 숫자라고 가정하지 않는다.
