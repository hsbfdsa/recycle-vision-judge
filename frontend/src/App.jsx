
import { useState, useEffect } from "react";
import JudgeResult from "./components/JudgeResult";
import { judgeImage, isMock, wakeServer } from "./services/judgeApi";
import "./App.css";

const MOCK_STATUSES = [
  "pass",
  "need_action",
  "retake",
  "question",
  "fallback",
  "different_item",
  "unsupported",
];

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  const [attempt, setAttempt] = useState(1);
  const [firstFile, setFirstFile] = useState(null);
  const [firstItem, setFirstItem] = useState(null);

  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [mockStatus, setMockStatus] = useState("pass");
  const [showMockTest, setShowMockTest] = useState(false);

  useEffect(() => {
    wakeServer();
  }, []);

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
    event.target.value = "";

    if (!selected) return;

    if (
      !selected.type.startsWith("image/") &&
      !/\.(heic|heif)$/i.test(selected.name)
    ) {
      setError("이미지 파일만 선택할 수 있어요.");
      return;
    }

    setFile(selected);
    setResult(null);
    setError("");

    runJudge(answers, null, selected);
  }

  // AI 판정
  async function runJudge(
    nextAnswers = answers,
    reuseObservation = null,
    imageOverride = file
  ) {
    if (!imageOverride) {
      setError("먼저 사진을 선택해 주세요.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const isRetake = attempt > 1;

      const data = await judgeImage({
        image: imageOverride,
        attempt,
        prevImage: isRetake ? firstFile : null,
        prevItem: isRetake ? firstItem : null,
        answers: nextAnswers,
        observation: reuseObservation,
        mockStatus,
      });

      if (!isRetake && data.judgement.status !== "unsupported") {
        setFirstFile(imageOverride);
        setFirstItem(data.judgement.item);
      }

      setResult(data);
    } catch (err) {
      setError(err.message || "오류가 발생했어요.");
    } finally {
      setLoading(false);
    }
  }

  // 질문 답변
  function handleAnswer(key, value) {
    const next = { ...answers, [key]: value };
    setAnswers(next);

    runJudge(
      next,
      key === "item_hint"
        ? null
        : result?.observation ?? null
    );
  }

  // 재촬영
  function handleRetake(countsAsAttempt) {
    if (countsAsAttempt) {
      setAttempt((prev) => prev + 1);
    }

    const checkedBox = (
      result?.judgement?.checklist ?? []
    ).some((item) => item.key === "checkbox");

    setAnswers((prev) => {
      const next = { ...prev };

      delete next.confirm_same_item;

      if (countsAsAttempt && checkedBox) {
        next.checkbox = "true";
      }

      return next;
    });

    setFile(null);
    setResult(null);
    setError("");
  }

  // 처음으로 돌아가기
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
    <main className="main-container">

      <section className={`workspace ${file ? "has-result" : ""}`}>

        {/* 사진 영역: 업로드 전후에도 같은 창을 유지 */}
        <div className={`upload-area upload-card ${file ? "photo-card" : ""}`}>

          <div className="brand">
            <span className="brand-icon">🌱</span>
            <span>RE:SCAN</span>
          </div>

          <div className="upload-title">
            <h2>오늘도 올바르게 🌿</h2>
            <p>
              {file
                ? "분리배출 결과를 확인해 보세요!"
                : "버릴 준비가 되었나요?"}
            </p>
          </div>

        {/* 사진 업로드 전 */}
        {!file && (
          <div className="upload-placeholder">
            <span className="camera-icon material-symbols-outlined">
              photo_camera
            </span>
            <p>사진을 업로드 해 주세요</p>
          </div>
        )}

        {/* 사진 미리보기 */}
        {file && preview && (
          <div className="preview">
            <img src={preview} alt="업로드한 사진" />
          </div>
        )}

        <label className={`upload-button ${file ? "retake-button" : ""}`}>
          {file ? "다시 촬영하기" : (
            <>
              <span className="upload-icon material-symbols-outlined">
                upload
              </span>
              사진 업로드하기
            </>
          )}

          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileChange}
          />
        </label>

          {!file && error && (
            <p className="error">{error}</p>
          )}

        </div>

        {/* 사진 업로드 후 오른쪽에 나타나는 AI 결과 */}
        {file && (
          <div className="judgement-panel">

            <JudgeResult
              key={`${attempt}-${result?.judgement?.status}`}
              result={result}
              loading={loading}
              onRetake={handleRetake}
              onAnswer={handleAnswer}
              onRestart={handleRestart}
            />

            {error && (
              <p className="error">{error}</p>
            )}

            {isMock && showMockTest && (
              <div className="mock-test">
                <select
                  value={mockStatus}
                  onChange={(e) => setMockStatus(e.target.value)}
                >
                  {MOCK_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            )}

          </div>
        )}

      </section>

    </main>
  </div>
);
}

export default App;
