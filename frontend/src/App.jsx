import { useState, useEffect } from "react";
import JudgeResult from "./components/JudgeResult";
import { judgeImage, isMock } from "./services/judgeApi";
import "./App.css";

const MOCK_STATUSES = ["pass", "need_action", "retake", "question", "fallback", "different_item", "unsupported"];

function App() {
  const [file, setFile] = useState(null);         // 지금 찍은 사진
  const [preview, setPreview] = useState(null);
  const [attempt, setAttempt] = useState(1);      // 몇 번째 촬영인지
  const [firstFile, setFirstFile] = useState(null); // 처음 찍은 사진 (재촬영 전후 비교용)
  const [firstItem, setFirstItem] = useState(null); // 처음 판정된 품목 (같은 물건인지 확인용)
  const [answers, setAnswers] = useState({});     // 질문 답
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mockStatus, setMockStatus] = useState("pass");
  const [showMockTest, setShowMockTest] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function handleFileChange(event) {
    const selected = event.target.files[0];
    event.target.value = ""; // 같은 파일 다시 선택 가능
    if (!selected) return;
    if (!selected.type.startsWith("image/") && !/\.(heic|heif)$/i.test(selected.name)) {
      setError("이미지 파일만 선택할 수 있어요.");
      return;
    }
    setFile(selected);
    setResult(null);
    setError("");
  }

  // reuseObservation: 질문에 답할 때 직전 AI 관찰을 다시 써서 AI 호출을 생략
  async function runJudge(nextAnswers = answers, reuseObservation = null) {
    if (!file) {
      setError("먼저 사진을 찍거나 선택해 주세요.");
      return;
    }
    try {
      setLoading(true);
      setError("");
      const isRetake = attempt > 1;
      const data = await judgeImage({
        image: file,
        attempt,
        prevImage: isRetake ? firstFile : null,
        prevItem: isRetake ? firstItem : null,
        answers: nextAnswers,
        observation: reuseObservation,
        mockStatus,
      });
      // 첫 촬영에서 지원 품목이 나오면 "처음 사진"으로 기억
      if (!isRetake && data.judgement.status !== "unsupported") {
        setFirstFile(file);
        setFirstItem(data.judgement.item);
      }
      setResult(data);
    } catch (err) {
      setError(err.message || "오류가 발생했어요.");
    } finally {
      setLoading(false);
    }
  }

  // 질문에 답하면 같은 사진으로 다시 판정 (촬영 횟수는 그대로)
  function handleAnswer(key, value) {
    const next = { ...answers, [key]: value };
    setAnswers(next);
    runJudge(next, result?.observation ?? null);
  }

  // countsAsAttempt: 처리 후 재촬영이면 true, 다른 물건을 찍어서 다시 찍는 거면 false
  function handleRetake(countsAsAttempt) {
    if (countsAsAttempt) setAttempt((prev) => prev + 1);
    // 질문에 '아니요'해서 체크리스트가 된 항목은, 처리했다고 했으니 다음 촬영에서 다시 물어본다
    const handledKeys = (result?.judgement?.checklist ?? []).map((item) => item.key);
    setAnswers((prev) =>
      Object.fromEntries(Object.entries(prev).filter(([key]) => !handledKeys.includes(key)))
    );
    setFile(null);
    setResult(null);
    setError("");
  }

  function handleRestart() {
    setFile(null);
    setAttempt(1);
    setFirstFile(null);
    setFirstItem(null);
    setAnswers({});
    setResult(null);
    setError("");
  }

  return (
    <div className="app">
      <div className="site">
      <h2>오늘도 올바르게</h2>
      <p>버릴 준비가 되었나요?</p>
      {!result && (
        <>
        <div className="upload-area">
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileChange}
          />
          {preview && (
            <div className="preview">
              <img src={preview} alt="업로드한 사진" />
            </div>
          )}
        </div>
        </>
      )}

      {error && <p className="error">{error}</p>}

      {/* 판정 버튼 + Mock 선택창 */}
      <div className="action-row">
      {!result && (
        <button onClick={() => runJudge()} disabled={!file || loading}>
          {loading ? "AI가 확인하는 중..." : "판정하기"}
        </button>
      )}
      </div>

        {isMock && showMockTest && (
          <div className="mock-test">
            <select
              value={mockStatus}
              onChange={(e) => setMockStatus(e.target.value)}
            >
              {MOCK_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        )}
      </div>
      
      <JudgeResult
        key={`${attempt}-${result?.judgement?.status}`}
        result={result}
        loading={loading}
        onRetake={handleRetake}
        onAnswer={handleAnswer}
        onRestart={handleRestart}
      />
    </div>
  );
}

export default App;
