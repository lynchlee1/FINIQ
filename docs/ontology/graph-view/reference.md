# Graph View Reference

## 구현 경로

**backend** — `src/finiq/`

## 기능 사양

### 그래프 표시와 내보내기

- 회사 공시 시간선은 서버가 반환한 `timeline` 순서를 유지하며 앞 80개 공시만 사용한다.
- graph JSON에는 node와 edge를 주고받는 데 필요한 주요 값만 저장한다.
- KO 위험도는 수동 기본값이 아닌 node를 대상으로 최대 3번 전파한다.

### 배치와 pin

- layout JSON에는 화면에 보이는 node 위치만 저장한다.
- layout JSON을 다시 읽을 때 저장된 위치가 있는 node만 고정한다.
- 기본 pin 한도는 3개다.
