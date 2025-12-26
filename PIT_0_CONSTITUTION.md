## 0. Naming & Scope
# ------------------------------------------------------------
# [목적]
# - 이름 때문에 헷갈려서 사고 나는 걸 원천 차단
# - AWS / systemd / Python import / 경로 혼선 방지
#
# [의미]
# - vella_v7 이 최상위 기준 이름이다
# - 다른 표기법은 전부 금지
# ------------------------------------------------------------
- Root project name is **vella_v7** (underscore only).
- All future V-series live under **vella_v7**.
- Hyphen is used ONLY for sub-roles (e.g., vella_v7-app).


## 1. Position
# ------------------------------------------------------------
# [목적]
# - V3의 결합도 높은 사고방식이 다시 스며드는 것을 차단
# - V4 설계를 "개념 입력"으로만 사용하도록 고정
#
# [중요]
# - V3는 참고용으로라도 다시 보지 않는다
# - 벨라가 "V3에서는..." 이라는 말을 꺼내는 순간 위반
# ------------------------------------------------------------
- V3 is **reference-frozen** and MUST NOT be reimplemented or consulted during coding.
- V4 **design and core concepts** are the ONLY conceptual inputs.
- V7 is a **new engine**, generated via PIT, not a refactor.


## 2. Non-goals
# ------------------------------------------------------------
# [목적]
# - V4 / V5에서 반복되었던 "임시조치 → 누적 붕괴" 방지
#
# [의미]
# - 편의성, 속도, 임시 성공을 이유로 구조를 망가뜨리지 않는다
# ------------------------------------------------------------
- No backward compatibility with V4/V5 code.
- No partial patching or hot-fixes.
- No mixed logic across sections.


## 3. Architecture Principles
# ------------------------------------------------------------
# [목적]
# - V3의 최대 약점이었던 "하나 고치면 다 고쳐야 하는 구조" 제거
#
# [핵심 철학]
# - 각 모듈은 서로를 모른다
# - 계약(contract)으로만 대화한다
#
# [주의]
# - 여기 어기면 V7은 바로 실패작이다
# ------------------------------------------------------------
- Modules are independent:
  - Context    # 시장 상태 / 레짐 / 환경 인식
  - Entry      # 진입 판단만 담당
  - Exit       # 청산 판단만 담당
  - Risk       # 손절, 비중, 리스크 계산
  - State      # 포지션 상태 기록 (판단 금지)
  - Execution  # 실제 주문 실행 (전략 판단 금지)

- Modules communicate **only via explicit contracts**.
- Changing one module MUST NOT require changes in others.


## 4. Configuration Rules
# ------------------------------------------------------------
# [목적]
# - CFG 숫자 튜닝하다가 구조가 무너지는 사고 방지
#
# [의미]
# - CFG는 "리모컨"이지 "엔진"이 아니다
# - 전략 로직을 CFG로 만들지 않는다
# ------------------------------------------------------------
- CFG defines **behavior switches**, not logic.
- CFG expansion is allowed ONLY at declared extension points.
- No hidden coupling via shared state.


## 5. Development Rules
# ------------------------------------------------------------
# [목적]
# - 즉석 수정, 감각 수정, 손코딩으로 인한 구조 오염 방지
#
# [중요]
# - 코드를 직접 고치고 싶어질 때가 가장 위험한 순간
# ------------------------------------------------------------
- All code is generated or regenerated from PIT documents.
- Manual edits to generated code are **forbidden**.
- Any change requires updating PIT first, then regenerating.


## 6. Ownership
# ------------------------------------------------------------
# [목적]
# - 역할 혼동 방지
#
# [의미]
# - 주인님: 전략 의도, 제약, 철학 결정
# - 벨라: 구현, 구조 유지, 일관성 책임
# ------------------------------------------------------------
- Human defines intent, constraints, and contracts.
- BELLA generates implementation.
- PIT is the single source of truth.


## 7. Enforcement
# ------------------------------------------------------------
# [목적]
# - 애매함, 추정, 요령을 완전히 금지
#
# [실무 번역]
# - "아마 이럴 것" → 삭제
# - "코드는 되는데…" → PIT 기준으로 다시 생성
# ------------------------------------------------------------
- If ambiguity arises, prefer deletion over assumption.
- If conflict arises, PIT overrides code.
