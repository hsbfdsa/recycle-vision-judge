# ♻️ AI 분리배출 판정 도우미

> 2026 연합 해커톤 23팀 · 2026.11 ~ 진행 중 · 백엔드 담당
>
> 사진 한 장으로 **지금 버려도 되는지**, 아니면 라벨 제거나 헹굼처럼 **무엇을 먼저 해야 하는지** 알려 주는 서비스

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![OpenAI](https://img.shields.io/badge/OpenAI-Vision-black)
![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react)

---

## 📌 Overview

분리배출 기준은 품목마다, 그리고 같은 품목이라도 상태마다 다릅니다. 투명 페트병은 라벨을 떼고 비워야 전용 수거함에 넣을 수 있고, 컵라면 용기는 음식물과 빨간 기름 자국이 남아 있으면 재활용이 어렵습니다.

이 서비스는 사진을 보고 **배출 방법**과 **버리기 전에 해야 할 처리**를 알려 주고, 처리 후 다시 찍으면 같은 물건인지 확인해 다시 판정합니다.

**지원 품목 (현재 4개)**

| 품목 | 판정 방식 |
| --- | --- |
| 투명 페트병 | 상태 확인 (투명 여부, 라벨, 내용물, 헹굼) |
| 컵라면 용기 | 상태 확인 (음식물, 빨간 기름 자국) |
| 깨진 유리 | 배출 방법 안내 |
| 영수증 | 배출 방법 안내 |

---

## 🏗 Architecture

**핵심 원칙: AI는 사진에서 보이는 것만 관찰하고, 판정은 규칙표가 내립니다.**

```
[사진]
   │  재촬영이면 처음 사진도 함께
   ▼
vision.py   OpenAI Vision 모델이 "보이는 것"만 JSON으로 관찰
   │        품목 · 확신도 · 라벨 · 내용물 · 음식물 · 기름 자국 · 같은 물건 여부
   ▼
schemas.py  Pydantic으로 관찰 결과 검사 (형식이 틀리면 실패, 모르는 값은 unknown)
   ▼
judge.py    rules.json 규칙표로 판정 (AI는 판정에 관여하지 않음)
   ▼
[7가지 상태 중 하나] → React 화면이 상태별로 분기
```

| 상태 | 의미 |
| --- | --- |
| `pass` | 그대로 배출 가능 |
| `need_action` | 처리가 필요함 (예: 라벨 제거) → 처리 후 재촬영 |
| `retake` | 사진으로 확인이 안 됨 → 다시 찍기 |
| `question` | 사진으로 알 수 없음 → 사용자에게 질문 (예: 헹구셨나요?) |
| `fallback` | 3번 찍어도 해결되지 않음 → 대체 배출 방법 안내 |
| `different_item` | 재촬영한 물건이 처음과 다름 |
| `unsupported` | 지원하지 않는 품목 |

---

## 🧠 Design Decisions

| 결정 | 이유 | 결과 |
| --- | --- | --- |
| **AI는 관찰만, 판정은 규칙표** | LLM이 배출 기준을 지어내는 것을 막고, 기준이 바뀌면 코드 대신 `rules.json`만 수정하기 위해 | 모르는 값은 `unknown` → 재촬영이나 질문으로 안전하게 처리 |
| **Flask → FastAPI + Pydantic** | 요청 · 응답 · AI 답 · 규칙표의 형식을 코드로 강제하기 위해 | 규칙표 오타는 서버가 켜질 때 차단, `/docs`에 API 문서 자동 생성 |
| **사진으로 모르는 건 질문** | 헹굼 여부는 사진으로 판단할 수 없고, 품목을 잘못 볼 수 있음 | 확신도 0.6 미만이면 "사진 속 물건이 ○○ 맞나요?" 확인 질문 |
| **질문 답변 시 관찰 재사용** | 같은 사진으로 AI를 다시 부르면 느리고, 답이 바뀌어 질문이 흔들림 | 답변 요청의 AI 호출 0회 (테스트로 검증) |
| **설정값 · 문구 분리** | 기획팀이 코드 없이 문구를 고치고, 실험값을 바꿀 수 있게 | 문구는 `rules.json`, 설정은 `config.py`와 `.env` |

---

## 🧪 Testing

AI를 호출하지 않는 자동 테스트 3종으로, 변경할 때마다 기존 동작이 깨지지 않았는지 확인합니다.

| 테스트 | 내용 | 결과 |
| --- | --- | --- |
| `tests/test_judge.py` | 판정 규칙 (관찰 → 상태) | 17 / 17 통과 |
| `tests/test_api.py` | API 요청 · 응답 · 오류 형식 (가짜 AI 사용) | 12 / 12 통과 |
| `tests/test_edge_cases.py` | 이상한 AI 값, 이상한 답변, 업로드, 규칙표 실수 등 경계 상황 39개 | 안전장치 27 통과 · 알려진 문제 12개 추적 |

`test_edge_cases.py`는 **아직 고치지 않은 알려진 문제**도 케이스로 남겨 둡니다. 고치면 "★ 고쳐짐"으로 바뀌어, 무엇이 남았는지 항상 보입니다.

`tests/run_tests.py`는 실제 사진으로 AI 관찰 정확도를 측정합니다 (API 키 필요).

```bash
python tests/test_judge.py
python tests/test_api.py
python tests/test_edge_cases.py
```

---

## 🔧 Troubleshooting

**1. 테스트는 통과했는데 AI가 품목을 잘못 배우고 있었음**
규칙표의 품목 설명으로 AI 프롬프트를 만들도록 바꾼 뒤, 테스트는 모두 통과했지만 실제 프롬프트를 출력해 보니 깨진 유리와 영수증의 설명이 서로 바뀌어 있었습니다. 테스트가 확인하지 못하는 부분은 **결과물을 직접 출력해 확인**하는 단계를 추가했습니다.

**2. 규칙표 오타가 조용히 판정을 망가뜨리는 문제**
`rules.json`의 필드 이름이 틀리면 오류 없이 엉뚱한 판정이 나올 수 있었습니다. Pydantic 스키마로 규칙표를 검사해, 오타가 있으면 **서버가 켜지지 않도록** 했습니다.

---

## 🚀 Getting Started

```bash
# 백엔드
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # OPENAI_API_KEY 입력
cd backend && python app.py               # http://127.0.0.1:5001/docs

# 프론트엔드 (다른 터미널)
cd frontend && npm install && npm run dev  # http://localhost:5173
```

- 프론트의 `VITE_USE_MOCK=true`로 두면 백엔드와 API 키 없이 7가지 화면을 모두 확인할 수 있습니다.
- Mock 응답은 `python tests/make_mock.py`로 실제 판정 코드에서 생성합니다.

---

## 📂 Project Structure

```
├── backend/
│   ├── app.py          # FastAPI 서버 (/judge, /health), 오류 형식 통일, 요청 로그
│   ├── vision.py       # 이미지 전처리 + AI 관찰
│   ├── judge.py        # 규칙표 기반 판정
│   ├── schemas.py      # Pydantic 스키마 (요청 · 응답 · 관찰 · 규칙표)
│   ├── rules.json      # 품목별 규칙, 화면 문구
│   ├── config.py       # 설정값 (.env로 변경 가능)
│   └── API.md          # 프론트 ↔ 백엔드 약속
├── frontend/           # React (Vite)
└── tests/              # 자동 테스트, Mock 생성, 정확도 측정
```

---

## 🗺 Roadmap

교수님 피드백(LLM 이미지 인식은 느리고, 같은 사진에도 답이 달라질 수 있음)을 반영해 진행 중입니다.

- [ ] **경량 이미지 모델로 전환**: 투명 페트병 4클래스(라벨 없음 · 라벨 있음 · 유색 · 기타)로 범위를 줄여 CNN 전이학습
- [ ] **같은 테스트셋으로 LLM vs CNN 비교**: 정확도, 틀린 단정, 응답 시간
- [ ] 관찰과 판정이 분리돼 있어 관찰 부분만 교체 (판정 · 규칙 · 화면은 그대로)
- [ ] 비동기 AI 호출, 업로드 전 사진 축소
- [ ] 배포 후 요청 로그로 실제 사용 개선

---

## 👨‍💻 My Role (Backend)

- 관찰과 판정을 분리한 백엔드 구조 설계
- Flask → FastAPI 전환, Pydantic 스키마 설계
- 규칙 엔진(`judge.py`)과 규칙표 구조, 질문 · 품목 확인 흐름
- 자동 테스트 3종, Mock 자동 생성, 정확도 측정 스크립트
- 업로드 크기 · 픽셀 제한, 요청 로그 등 운영 장치

## 👥 Team

2026 연합 해커톤 23팀 
