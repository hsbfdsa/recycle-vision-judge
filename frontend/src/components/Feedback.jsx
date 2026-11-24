import { useState } from "react";
import { sendFeedback } from "../services/judgeApi";

// 결과 화면 아래 "판정이 맞았나요?" — 모인 '틀렸어요'는 평가 세트 후보가 된다 (tests/export_feedback.py)
const REASONS = [
  { value: "item", label: "품목이 틀렸어요" },
  { value: "state", label: "상태를 잘못 봤어요" },
  { value: "place", label: "버리는 곳이 달라요" },
  { value: "other", label: "기타" },
];

function Feedback({ judgmentId }) {
  const [mode, setMode] = useState("ask");       // ask → wrong(이유 고르기) → done
  const [sending, setSending] = useState(false);
  const [reason, setReason] = useState(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");

  async function submit(correct) {
    setSending(true);
    setError("");
    try {
      await sendFeedback({ judgmentId, correct, reason: correct ? null : reason, comment: correct ? "" : comment });
      setMode("done");
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  if (mode === "done") {
    return <p className="feedback-done">의견 고마워요. 판정을 고치는 데 쓸게요.</p>;
  }

  return (
    <div className="feedback">
      {mode === "ask" ? (
        <>
          <p className="feedback-q">판정이 맞았나요?</p>
          <div className="feedback-row">
            <button type="button" disabled={sending} onClick={() => submit(true)}>맞았어요</button>
            <button type="button" className="secondary" disabled={sending} onClick={() => setMode("wrong")}>틀렸어요</button>
          </div>
        </>
      ) : (
        <>
          <p className="feedback-q">무엇이 틀렸나요?</p>
          <div className="feedback-reasons" role="radiogroup" aria-label="틀린 부분">
            {REASONS.map((r) => (
              <button key={r.value} type="button" role="radio" aria-checked={reason === r.value}
                className={reason === r.value ? "chip on" : "chip"} onClick={() => setReason(r.value)}>
                {r.label}
              </button>
            ))}
          </div>
          <textarea
            maxLength={300}
            rows={2}
            aria-label="의견 (선택)"
            placeholder="어떻게 버려야 맞는지 알려 주시면 도움이 돼요 (선택)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="feedback-row">
            <button type="button" disabled={!reason || sending} onClick={() => submit(false)}>보내기</button>
            <button type="button" className="secondary" disabled={sending} onClick={() => setMode("ask")}>취소</button>
          </div>
        </>
      )}
      {error && <p className="feedback-error" role="alert">{error}</p>}
      <p className="feedback-note">사진은 저장하지 않아요. 판정 결과와 의견만 남아요.</p>
    </div>
  );
}

export default Feedback;
