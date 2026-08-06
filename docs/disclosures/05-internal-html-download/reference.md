# 본문 HTML 저장 Reference

## 경로와 형식

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
