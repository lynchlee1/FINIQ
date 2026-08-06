# 제목 조회와 공시 선택 Reference

## 경로와 형식

- 입력 경로는 `<data_root>/02-table`, 원본 저장 경로는 `<data_root>/03-filter/<workflow-name>.json`이다. 조건, 실행 상태, 완료 결과 또는 중단 결과를 한 JSON에서 관리한다.
- 현재 04단계 연결을 위해 `<data_root>/03-filter/<mode>/filtered.json`도 만든다. 이 파일은 원본 결과에서 만든 파생 전달 파일이다.
```text
<data_root>/
├── 02-table/
│   ├── <YYYY>.sqlite
│   └── sqlite_manifest.json
└── 03-filter/
    ├── <workflow-name>.json       # 조건·상태·결과 원본
    ├── ...
    └── <mode>/filtered.json       # 04단계 호환용 파생 파일
```

- `03-filter` 바로 아래에는 `filtered.json`을 만들지 않는다.

## 상태와 값

- 실행 상태는 대기 `ready`, 실행 중 `running`, 중단 `interrupted`, 완료 `completed`, 실패 `failed`다.
