# Graph View 그래프 동작

## 대규모 인수 관계 축약

- `ACQUIRED` edge가 `collapse_minor_threshold`를 넘으면 가중치가 큰 3개를 남기고 나머지를 합계 node와 edge로 묶는다.

## pin과 표시

- 기본 pin 한도는 3개다. node를 누르거나 옮겨 한도를 넘으면 가장 오래전에 pin한 node부터 자동으로 해제하며 이후 graph·layout JSON을 내보내면 현재 pin 상태가 저장된다.
- 그래프 이름이 너무 길면 끝을 `…`로 줄이고 방문 기록은 최근 10개만 보여 준다. 원본 그래프는 바꾸지 않는다.

## 구현 경로

**backend** — `src/finiq/`

## 그래프 표시와 내보내기

- 회사 공시 시간선은 서버가 반환한 `timeline` 순서를 유지하며 앞 80개 공시만 사용한다.
- graph JSON에는 node와 edge를 주고받는 데 필요한 주요 값만 저장한다.
- KO 위험도는 수동 기본값이 아닌 node를 대상으로 최대 3번 전파한다.

## 배치와 pin

- layout JSON에는 화면에 보이는 node 위치만 저장한다.
- layout JSON을 다시 읽을 때 저장된 위치가 있는 node만 고정한다.
- 기본 pin 한도는 3개다.
