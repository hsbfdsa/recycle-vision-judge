import responses from "./responses.json";
import { shrinkImage } from "./shrink";

// VITE_USE_MOCK=false 로 두면 실제 백엔드에 연결
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

// 개발 중: "/api" → vite.config.js 프록시가 http://127.0.0.1:5001 로 전달
// 배포 후: VITE_API_BASE_URL=https://백엔드주소
// 끝에 "/"를 붙여 넣어도 "//judge"가 되지 않게 제거
const API_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");

export const isMock = USE_MOCK;

// 무료 배포 서버는 한동안 안 쓰면 잠든다. 앱을 열자마자 깨워 두면, 사진을 찍는 동안 켜진다.
export function wakeServer() {
  if (!USE_MOCK) fetch(`${API_URL}/health`).catch(() => {});
}

// "품목이 달라요" 버튼용 품목 목록 (자주 찾는 품목이 앞). 실패하면 빈 목록
export async function getItems() {
  if (USE_MOCK) {
    const q = responses.unsupported.judgement.questions.find((x) => x.key === "item_hint");
    return { text: q?.text ?? "찍은 물건이 무엇인가요?", items: q?.options ?? [] };
  }
  try {
    const res = await fetch(`${API_URL}/items`);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch {
    return { text: "", items: [] };
  }
}

export async function judgeImage({ image, attempt, prevImage = null, prevItem = null, answers = {}, observation = null, mockStatus = "pass" }) {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 400)); // 로딩 화면 확인용
    const mock = structuredClone(Object.keys(answers).length ? responses.pass : responses[mockStatus]);
    mock.judgement.attempt = attempt;
    return mock;
  }

  const formData = new FormData();
  if (observation) {
    // 질문 답변: 사진 대신 직전 관찰을 보내면 서버가 AI를 다시 부르지 않음 (빠르고 비용 0)
    formData.append("observation", JSON.stringify(observation));
  } else {
    // 올리기 전에 긴 변 1024px로 줄임 (휴대폰 원본 수 MB → 수백 KB, 업로드가 빨라짐)
    formData.append("image", await shrinkImage(image));
  }
  formData.append("attempt", String(attempt));
  if (prevImage && !observation) formData.append("prev_image", await shrinkImage(prevImage));
  if (prevItem) formData.append("prev_item", prevItem);
  if (Object.keys(answers).length) formData.append("answers", JSON.stringify(answers));

  let response;
  try {
    response = await fetch(`${API_URL}/judge`, { method: "POST", body: formData });
  } catch {
    throw new Error("서버에 연결할 수 없어요. 백엔드가 켜져 있는지 확인해 주세요.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // 백엔드 오류 형식: {"error": {"code": "...", "message": "..."}}
    throw new Error(data?.error?.message || "판정 요청에 실패했어요.");
  }
  return data;
}

// 결과 화면의 "맞았어요 / 틀렸어요". judgmentId는 판정 응답의 judgment_id
export async function sendFeedback({ judgmentId, correct, reason = null, comment = "" }) {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 300));
    return { ok: true };
  }
  let response;
  try {
    response = await fetch(`${API_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ judgment_id: judgmentId, correct, reason, comment: comment.trim() || null }),
    });
  } catch {
    throw new Error("서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || "의견을 보내지 못했어요.");
  return data;
}
