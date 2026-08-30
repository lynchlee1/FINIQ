# 07 진단과 조회

## 필드 상태

일부 mode는 각 업무값을 얼마나 확실하게 읽었는지 `field_parse_status`에 기록한다.

| 상태 | 뜻 |
| --- | --- |
| `parsed` | 정해진 위치에서 유효한 값을 읽음 |
| `explicit_zero` | 원문에 0 또는 이 field에서 0으로 인정하는 `-`가 적혀 있음 |
| `source_not_found` | 정해진 위치에서 값을 찾지 못함 |
| `not_applicable` | 해당 공시 유형에는 적용하지 않는 field라서 찾지 않음 |

`source_not_found`는 “일부 값을 찾지 못했다”는 상태이지 파일 전체의 parsing 실패를 뜻하지 않는다. mode가 반드시 필요로 하는 표가 없거나 입력 형식 자체가 잘못된 경우에만 파일 오류가 된다.

## 경고와 오류

warning은 record를 저장할 수 있지만 확인이 필요한 경우이고, error는 해당 파일의 record를 만들지 못한 경우다.

### warning 항목

| 항목 | 의미 |
| --- | --- |
| `index`, `total` | 전체 입력에서 현재 파일의 순서와 입력 수 |
| `mode`, `acpt_no` | parser mode와 원본 공시 식별값 |
| `warning` | 사람이 확인할 warning 문장 |
| `level` | `weak_warning`, `medium_warning`, `strong_warning` 중 하나 |
| `warning_code` | 전용 code, `source_not_found:<field>` 또는 일반 `parse_warning` |

한 record의 `parse_warnings`는 수준별 warning 목록과 같은 문장 집합이어야 한다. 빈 문장, 중복 문장, 수준이 없는 문장, 두 수준에 동시에 들어간 문장이 있으면 저장 전에 실패한다.

### 오류 항목

`errors[]`의 각 항목은 `index`, `total`, `mode`, `acpt_no`, `error_type`, `error`를 가진다.

- `skip_errors=true`: 오류를 `errors`에 넣고 다음 파일을 처리한다.
- `skip_errors=false`: 첫 파일 오류에서 전체 실행을 중단하고 최종 결과를 저장하지 않는다.

## 정정공시 묶음

correction family는 최초 공시와 이후 정정공시를 한 묶음으로 표현한다.

```text
records[]
└── family_id, current_sequence, family_member_count

families[family_id]
└── members[]
    └── sequence, acpt_no, doc_no, title, disclosed_at, is_correction_report
```

각 record에는 어느 family의 몇 번째 문서인지만 기록한다. 구성원 전체 정보는 최상위 `families[family_id].members`에 한 번만 둔다. 필요한 구성원을 모두 연결하지 못하면 불완전한 family를 만들지 않는다.

## 미리보기와 검사

| 기능 | 입력과 결과 |
| --- | --- |
| Preview | `mode`, `input_directory`, 선택 metadata 경로, `filter_blocks`, `limit`을 받아 record를 보여 줌; `limit` 기본값은 3 |
| Source preview | 한 preview record 안에서 원문 표를 최대 12개, 전체 120행까지 보여 주고 나머지 행 수를 기록 |
| Filter candidates | `mode`, `input_directory`, `field`와 선택 metadata 경로·`parallel_workers`를 받아 값별 전체 건수와 최대 20개의 `acpt_no` 예시를 반환 |
| Cancel | 비어 있지 않은 `cancel_token`으로 새 작업 제출을 멈추고 이미 처리한 record를 저장; 제출을 마친 병렬 작업은 끝날 수 있음 |
| Excel export | 모든 record key를 열로 만들고 목록·객체는 JSON 문자열로 기록 |

preview record 하나가 공시 한 건을 나타낸다. 공시 식별값인 `acpt_no`는 그 record의 바깥쪽에 있고, 내부 `source_preview`에는 표와 생략 행 정보만 둔다.

사채 요약처럼 저장 결과와 원문 HTML을 함께 읽는 조회 요청은 결과 폴더와 `input_directory`를 각각 받는다. 조회 함수는 저장 JSON 안에서 원문 경로를 찾거나 결과 위치로 입력 위치를 추론하지 않는다.

`latest_only=true`로 Excel을 만들면 correction family마다 마지막 문서만 남기고 family가 없는 record는 그대로 유지한다. 08단계의 정정 내역 비교는 이 단계가 저장한 `families`와 record 순서를 사용한다.
