---
paths: ["tests/**", "src/**", "fluidattn/**"]
---
- 소스 모듈은 테스트 먼저(tdd-guard·pre-commit 이 강제, `tests/test_<module>.py`). 정상·엣지·에러 3케이스 최소.
- GPU 의존 테스트는 `pytest.mark.skipif(not torch.cuda.is_available())` 로 격리 — CPU 만으로 `pytest -q` 가 green 이어야 한다.
- 수치 비교는 `torch.testing.assert_close`(atol/rtol 명시). 참조 구현(naive attention) 대비 검증.
- 테스트 이름은 동작을 문장으로(`test_masks_future_positions`).
- 같은 테스트 3회 연속 실패 시 retry-lock 이 멈춘다 — 사람에게 원인을 보고하라.
- fix 커밋도 회귀 테스트 2종 — ① 실패 케이스 ② 정상 경로가 여전히 통과하는 케이스.
