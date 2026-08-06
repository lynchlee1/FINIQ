# KIND 조건검색 결과 저장 Reference

## 경로와 형식

- 저장 경로는 `<data_root>/01-list`이며 저장 형식은 아래와 같다.
- 하위 폴더 이름에는 연도별 시작일과 종료일을 YYYYMMDD 형식으로 기록한다.
```text
<data_root>/
└── 01-list/
    └── <YYYYMMDD>_<YYYYMMDD>/
        ├── *_post_page_*.body
        ├── kind_workflow.input.json
        └── kind_workflow.checkpoint.json
```
