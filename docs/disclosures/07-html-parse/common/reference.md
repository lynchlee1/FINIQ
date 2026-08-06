# 공시원문 변환 Reference

## 경로와 형식

- `/html-parse`에서 변환 유형을 선택해 parsing하거나 preview할 때 적용한다.
- 입력 HTML은 `<data_root>/06-sections/<year>/<acpt_no>.html`에서 읽으며 `<year>`는 4자리 숫자 폴더다. metadata는 `<data_root>/03-filter/<mode>/filtered.json`과 `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`에서 읽는다.
- 결과는 `<data_root>/07-converted/<mode>/parsed-<mode>.json`에 저장한다. 원본 HTML은 수정하지 않는다.

```text
<data_root>/
├── 03-filter/<mode>/filtered.json
├── 04-external-html-download/<mode>/compressed-external-html.json
├── 06-sections/<year>/<acpt_no>.html
└── 07-converted/<mode>/parsed-<mode>.json
```
