const API_BASE = window.location.origin;

const state = {
    selectedFile: null,
    quizData: null,
    questions: [],
    currentQuestion: 0,
    answers: [],
    questionCount: 10,
    difficulty: "mixed",
    summaryData: null,
    quizHistory: JSON.parse(localStorage.getItem("quizHistory") || "[]"),
};
const ANALYSIS_STEPS = [
    "Reading PDF content",
    "Identifying key topics",
    "Generating quiz questions",
    "Preparing your quiz",
];

const SUMMARY_STEPS = [
    "Reading PDF content",
    "Identifying key topics",
    "Summarizing content",
];

document.addEventListener("DOMContentLoaded", () => {
    setupUpload();
    setupSetupOptions();
});

document.addEventListener("DOMContentLoaded", () => {
    setupUpload();
    setupSetupOptions();
    renderDashboard();
});

function showPage(pageId) {
    document.querySelectorAll(".page").forEach((page) => page.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.page === pageId);
    });

    const page = document.getElementById(`page-${pageId}`);
    if (page) page.classList.add("active");

    if (pageId === "dashboard") renderDashboard();
}

function setupUpload() {
    const uploadArea = document.getElementById("upload-area");
    const fileInput = document.getElementById("file-input");

    fileInput.addEventListener("change", (event) => {
        const file = event.target.files[0];
        if (file) handleFileSelect(file);
    });

    uploadArea.addEventListener("dragover", (event) => {
        event.preventDefault();
        uploadArea.classList.add("dragover");
    });

    uploadArea.addEventListener("dragleave", () => {
        uploadArea.classList.remove("dragover");
    });

    uploadArea.addEventListener("drop", (event) => {
        event.preventDefault();
        uploadArea.classList.remove("dragover");
        const file = event.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    });
}
function handleFileSelect(file) {
    hideError();

    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showError("Please upload a PDF file.");
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        showError("File size must be under 10MB.");
        return;
    }

    state.selectedFile = file;
    document.getElementById("upload-content").style.display = "none";
    document.getElementById("file-info").style.display = "flex";
    document.getElementById("file-name").textContent = file.name;
    document.getElementById("file-size").textContent = formatFileSize(file.size);
    document.getElementById("upload-area").classList.add("has-file");
    document.getElementById("analyze-btn").disabled = false;
    document.getElementById("summarize-btn").disabled = false;
    document.getElementById("teacher-generate-btn").disabled = false;
}

function removeFile() {
    state.selectedFile = null;
    document.getElementById("file-input").value = "";
    document.getElementById("upload-content").style.display = "block";
    document.getElementById("file-info").style.display = "none";
    document.getElementById("upload-area").classList.remove("has-file");
    document.getElementById("analyze-btn").disabled = true;
    document.getElementById("summarize-btn").disabled = true;
    document.getElementById("teacher-generate-btn").disabled = true;
    hideError();
}
function setupSetupOptions() {
    bindOptionGroup("question-count-options", (value) => {
        state.questionCount = Number(value);
    });

    bindOptionGroup("difficulty-options", (value) => {
        state.difficulty = value;
    });
}

function bindOptionGroup(containerId, onSelect) {
    const container = document.getElementById(containerId);
    container.querySelectorAll(".setup-option").forEach((button) => {
        button.addEventListener("click", () => {
            container.querySelectorAll(".setup-option").forEach((item) => item.classList.remove("selected"));
            button.classList.add("selected");
            onSelect(button.dataset.value);
        });
    });
}

async function analyzePDF() {
    if (!state.selectedFile) return;

    hideError();
    document.getElementById("analyze-btn").disabled = true;
    document.getElementById("summarize-btn").disabled = true;
    document.getElementById("analyzing-title").textContent = "AI is reading your PDF...";
    document.getElementById("analyzing-subtitle").textContent = "Analyzing content and generating questions";
    document.getElementById("analyzing-state").style.display = "block";
    renderSteps(ANALYSIS_STEPS, 0);

    const formData = new FormData();
    formData.append("file", state.selectedFile);
    formData.append("question_count", String(state.questionCount));
    formData.append("difficulty", state.difficulty);

    try {
        renderSteps(ANALYSIS_STEPS, 1);
        const response = await fetch(`${API_BASE}/api/analyze`, {
            method: "POST",
            body: formData,
        });

        renderSteps(ANALYSIS_STEPS, 2);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Failed to analyze PDF.");
        }

        renderSteps(ANALYSIS_STEPS, 3);
        await wait(500);

        state.quizData = data;
        state.questions = data.questions || [];
        showQuizSetup(data);
    } catch (error) {
        showError(error.message || "Something went wrong while analyzing the PDF.");
    } finally {
        document.getElementById("analyzing-state").style.display = "none";
        document.getElementById("analyze-btn").disabled = false;
        document.getElementById("summarize-btn").disabled = false;
    }
}

async function summarizePDF() {
    if (!state.selectedFile) return;

    hideError();
    document.getElementById("analyze-btn").disabled = true;
    document.getElementById("summarize-btn").disabled = true;
    document.getElementById("analyzing-title").textContent = "AI is reading your PDF...";
    document.getElementById("analyzing-subtitle").textContent = "Summarizing content";
    document.getElementById("analyzing-state").style.display = "block";
    renderSteps(SUMMARY_STEPS, 0);

    const formData = new FormData();
    formData.append("file", state.selectedFile);

    try {
        renderSteps(SUMMARY_STEPS, 1);
        const response = await fetch(`${API_BASE}/api/summarize`, {
            method: "POST",
            body: formData,
        });

        renderSteps(SUMMARY_STEPS, 2);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Failed to summarize PDF.");
        }

        state.summaryData = data;
        showSummary(data);
    } catch (error) {
        showError(error.message || "Something went wrong while summarizing the PDF.");
    } finally {
        document.getElementById("analyzing-state").style.display = "none";
        document.getElementById("analyze-btn").disabled = false;
        document.getElementById("summarize-btn").disabled = false;
    }
}

function renderSteps(steps, activeIndex) {
    const container = document.getElementById("steps-container");
    container.innerHTML = steps.map((label, index) => {
        const status = index < activeIndex ? "complete" : index === activeIndex ? "active" : "";
        const icon = index < activeIndex ? "✓" : index === activeIndex ? "●" : "○";
        return `
            <div class="step ${status}">
                <div class="step-icon ${status}">${icon}</div>
                <span class="step-text">${label}</span>
                ${index < activeIndex ? '<span class="step-check">✓</span>' : ""}
            </div>
        `;
    }).join("");
}

function showQuizSetup(data) {
    showPage("quiz");
    document.getElementById("quiz-setup").style.display = "block";
    document.getElementById("quiz-interface").style.display = "none";

    document.getElementById("setup-stats").innerHTML = `
        <div class="setup-stat blue">
            <div class="setup-stat-label">Questions</div>
            <div class="setup-stat-value">${data.question_count}</div>
        </div>
        <div class="setup-stat pink">
            <div class="setup-stat-label">Topics</div>
            <div class="setup-stat-value">${data.topics.length}</div>
        </div>
        <div class="setup-stat green">
            <div class="setup-stat-label">Words Read</div>
            <div class="setup-stat-value">${data.word_count}</div>
        </div>
        <div class="setup-stat orange">
            <div class="setup-stat-label">Mode</div>
            <div class="setup-stat-value" style="font-size:16px;">${data.ai_mode === "openai" ? "AI" : "Local"}</div>
        </div>
    `;
}

function showSummary(data) {
    showPage("summary");
    document.getElementById("summary-doc-name").textContent = data.document_name || "Uploaded PDF";

    const summary = data.summary || { overview: "", key_points: [], definitions: [] };

    document.getElementById("summary-content").innerHTML = `
        <div class="setup-stats" style="margin-bottom: 24px;">
            <div class="setup-stat blue">
                <div class="setup-stat-label">Topics</div>
                <div class="setup-stat-value">${(data.topics || []).length}</div>
            </div>
            <div class="setup-stat green">
                <div class="setup-stat-label">Words Read</div>
                <div class="setup-stat-value">${data.word_count || 0}</div>
            </div>
            <div class="setup-stat orange">
                <div class="setup-stat-label">Mode</div>
                <div class="setup-stat-value" style="font-size:16px;">${data.ai_mode === "openai" ? "AI" : "Local"}</div>
            </div>
        </div>

        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>Overview</h3>
            <p>${escapeHtml(summary.overview || "No overview available.")}</p>
        </div>

        ${summary.key_points && summary.key_points.length ? `
        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>Key Points</h3>
            <ul style="padding-left: 20px; line-height: 1.8;">
                ${summary.key_points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}
            </ul>
        </div>` : ""}

        ${summary.definitions && summary.definitions.length ? `
        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>Key Terms</h3>
            <div class="dashboard-grid">
                ${summary.definitions.map((def) => `
                    <div class="dashboard-card">
                        <div class="dashboard-card-title">${escapeHtml(def.term)}</div>
                        <p style="margin-top: 8px; color: #64748B; font-size: 14px;">${escapeHtml(def.definition)}</p>
                    </div>
                `).join("")}
            </div>
        </div>` : ""}

        <div class="results-actions">
            <button class="btn-primary" onclick="showPage('upload')">Upload New PDF</button>
        </div>
    `;
}

function startQuiz() {
    if (!state.questions.length) return;

    state.currentQuestion = 0;
    state.answers = [];
    document.getElementById("quiz-setup").style.display = "none";
    document.getElementById("quiz-interface").style.display = "block";
    renderQuestion();
}

function renderQuestion() {
    const question = state.questions[state.currentQuestion];
    const total = state.questions.length;
    const progress = Math.round(((state.currentQuestion) / total) * 100);

    document.getElementById("progress-text").textContent = `Question ${state.currentQuestion + 1} of ${total}`;
    document.getElementById("progress-percent").textContent = `${progress}%`;
    document.getElementById("progress-fill").style.width = `${progress}%`;
    document.getElementById("q-number").textContent = `Question ${state.currentQuestion + 1} of ${total}`;
    document.getElementById("q-text").textContent = question.question;
    document.getElementById("q-topic").textContent = `Topic: ${question.topic || "General"}`;

    const difficultyEl = document.getElementById("q-difficulty");
    difficultyEl.textContent = question.difficulty || "medium";
    difficultyEl.className = `question-difficulty ${question.difficulty || "medium"}`;

    const letters = ["A", "B", "C", "D"];
    document.getElementById("options-container").innerHTML = question.options
        .map(
            (option, index) => `
                <button class="option" onclick="selectAnswer(${index})">
                    <span class="option-letter">${letters[index]}</span>
                    <span>${escapeHtml(option)}</span>
                </button>
            `
        )
        .join("");

    document.getElementById("feedback-container").innerHTML = "";
}

function selectAnswer(selectedIndex) {
    const question = state.questions[state.currentQuestion];
    const isCorrect = selectedIndex === question.correct_index;
    state.answers.push({ selectedIndex, isCorrect, question });

    document.querySelectorAll(".option").forEach((option, index) => {
        option.classList.add("disabled");
        option.onclick = null;
        if (index === question.correct_index) option.classList.add("correct");
        if (index === selectedIndex && !isCorrect) option.classList.add("incorrect");
        if (index === selectedIndex && isCorrect) option.classList.add("selected");
    });

    document.getElementById("feedback-container").innerHTML = `
        <div class="feedback-card ${isCorrect ? "correct" : "incorrect"}">
            <div class="feedback-header">
                <span>${isCorrect ? "✅" : "❌"}</span>
                <h3>${isCorrect ? "Correct!" : "Not quite"}</h3>
            </div>
            <p class="feedback-explanation">${
                escapeHtml(
                    isCorrect
                        ? (question.explanation || "Nice work.")
                        : (question.misconception || "Review the PDF content to understand this topic better.")
                )
            }</p>
            <div class="feedback-actions">
                <button class="btn-primary" onclick="nextQuestion()">
                    ${state.currentQuestion + 1 < state.questions.length ? "Next Question →" : "See Results"}
                </button>
            </div>
        </div>
    `;
}

function nextQuestion() {
    if (state.currentQuestion + 1 < state.questions.length) {
        state.currentQuestion += 1;
        renderQuestion();
        return;
    }
    showResults();
}

function showResults() {
    const correctCount = state.answers.filter((answer) => answer.isCorrect).length;
    const total = state.answers.length;
    const score = Math.round((correctCount / total) * 100);

    const topicStats = {};
    state.answers.forEach(({ isCorrect, question }) => {
        const topic = question.topic || "General";
        if (!topicStats[topic]) topicStats[topic] = { correct: 0, total: 0 };
        topicStats[topic].total += 1;
        if (isCorrect) topicStats[topic].correct += 1;
    });

    const topicBreakdown = Object.entries(topicStats).map(([topic, stats]) => {
        const pct = Math.round((stats.correct / stats.total) * 100);
        let strength;
        if (pct >= 70) strength = "strong";
        else if (pct < 50) strength = "weak";
        else strength = "moderate";
        return { topic, ...stats, pct, strength };
    });

    const strongTopics = topicBreakdown.filter((t) => t.strength === "strong").sort((a, b) => b.pct - a.pct);
    const weakTopics = topicBreakdown.filter((t) => t.strength === "weak").sort((a, b) => a.pct - b.pct);
    const moderateTopics = topicBreakdown.filter((t) => t.strength === "moderate");

    const result = {
        id: Date.now(),
        documentName: state.quizData?.document_name || "Uploaded PDF",
        score,
        correctCount,
        total,
        topics: state.quizData?.topics || [],
        topicBreakdown,
        date: new Date().toISOString(),
    };

    state.quizHistory.unshift(result);
    state.quizHistory = state.quizHistory.slice(0, 20);
    localStorage.setItem("quizHistory", JSON.stringify(state.quizHistory));

    showPage("results");
    document.getElementById("results-doc-name").textContent = result.documentName;
    document.getElementById("results-content").innerHTML = `
        <div class="score-circle">
            <div class="score-value">${score}%</div>
            <div class="score-label">Score</div>
        </div>
        <div class="results-stats">
            <div class="result-stat">
                <div class="result-stat-value">${correctCount}</div>
                <div class="result-stat-label">Correct</div>
            </div>
            <div class="result-stat">
                <div class="result-stat-value">${total - correctCount}</div>
                <div class="result-stat-label">Incorrect</div>
            </div>
            <div class="result-stat">
                <div class="result-stat-value">${total}</div>
                <div class="result-stat-label">Total Questions</div>
            </div>
        </div>

        ${strongTopics.length ? `
        <div class="topics-list" style="margin-bottom: 16px;">
            <h3>💪 Strong Topics</h3>
            <div class="topic-tags">
                ${strongTopics.map((t) => `
                    <span class="topic-tag" style="background:#DCFCE7; color:#166534;">
                        ${escapeHtml(t.topic)} — ${t.correct}/${t.total}
                    </span>
                `).join("")}
            </div>
        </div>` : ""}

        ${weakTopics.length ? `
        <div class="topics-list" style="margin-bottom: 16px;">
            <h3>⚠️ Needs Review</h3>
            <div class="topic-tags">
                ${weakTopics.map((t) => `
                    <span class="topic-tag" style="background:#FEE2E2; color:#991B1B;">
                        ${escapeHtml(t.topic)} — ${t.correct}/${t.total}
                    </span>
                `).join("")}
            </div>
        </div>` : ""}

        ${moderateTopics.length ? `
        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>Moderate</h3>
            <div class="topic-tags">
                ${moderateTopics.map((t) => `
                    <span class="topic-tag">
                        ${escapeHtml(t.topic)} — ${t.correct}/${t.total}
                    </span>
                `).join("")}
            </div>
        </div>` : ""}

        <div class="results-actions">
            <button class="btn-primary" onclick="startQuiz()">Retry Quiz</button>
            <button class="btn-secondary" onclick="showPage('upload')">Upload New PDF</button>
            <button class="btn-secondary" onclick="showPage('dashboard')">View Dashboard</button>
        </div>
    `;
}
function renderDashboard() {
    const container = document.getElementById("dashboard-content");
    if (!container) return;

    if (!state.quizHistory.length) {
        container.innerHTML = `
            <div class="dashboard-empty">
                <div class="dashboard-empty-icon">📚</div>
                <h3>No quizzes yet</h3>
                <p>Upload a PDF to generate your first AI-powered quiz.</p>
                <button class="btn-primary" onclick="showPage('upload')">Upload PDF</button>
            </div>
        `;
        return;
    }

    const totalQuizzes = state.quizHistory.length;
    const avgScore = Math.round(
        state.quizHistory.reduce((sum, item) => sum + item.score, 0) / totalQuizzes
    );
    const totalCorrect = state.quizHistory.reduce((sum, item) => sum + item.correctCount, 0);
    const totalQuestions = state.quizHistory.reduce((sum, item) => sum + item.total, 0);

    // Aggregate topic accuracy across all quizzes, not just per-quiz.
    const topicAgg = {};
    state.quizHistory.forEach((item) => {
        (item.topicBreakdown || []).forEach(({ topic, correct, total }) => {
            if (!topicAgg[topic]) topicAgg[topic] = { correct: 0, total: 0 };
            topicAgg[topic].correct += correct;
            topicAgg[topic].total += total;
        });
    });

    const topicList = Object.entries(topicAgg).map(([topic, stats]) => {
        const pct = Math.round((stats.correct / stats.total) * 100);
        let strength;
        if (pct >= 70) strength = "strong";
        else if (pct < 50) strength = "weak";
        else strength = "moderate";
        return { topic, ...stats, pct, strength };
    });

    const strongTopics = topicList.filter((t) => t.strength === "strong").sort((a, b) => b.pct - a.pct).slice(0, 8);
    const weakTopics = topicList.filter((t) => t.strength === "weak").sort((a, b) => a.pct - b.pct).slice(0, 8);

    container.innerHTML = `
        <div class="setup-stats" style="margin-bottom: 24px;">
            <div class="setup-stat blue">
                <div class="setup-stat-label">Quizzes Taken</div>
                <div class="setup-stat-value">${totalQuizzes}</div>
            </div>
            <div class="setup-stat green">
                <div class="setup-stat-label">Avg Score</div>
                <div class="setup-stat-value">${avgScore}%</div>
            </div>
            <div class="setup-stat pink">
                <div class="setup-stat-label">Questions Answered</div>
                <div class="setup-stat-value">${totalQuestions}</div>
            </div>
            <div class="setup-stat orange">
                <div class="setup-stat-label">Total Correct</div>
                <div class="setup-stat-value">${totalCorrect}</div>
            </div>
        </div>

        ${weakTopics.length ? `
        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>⚠️ Weakest Topics (across all quizzes)</h3>
            <div class="topic-tags">
                ${weakTopics.map((t) => `
                    <span class="topic-tag" style="background:#FEE2E2; color:#991B1B;">
                        ${escapeHtml(t.topic)} — ${t.correct}/${t.total} (${t.pct}%)
                    </span>
                `).join("")}
            </div>
        </div>` : ""}

        ${strongTopics.length ? `
        <div class="topics-list" style="margin-bottom: 24px;">
            <h3>💪 Strongest Topics (across all quizzes)</h3>
            <div class="topic-tags">
                ${strongTopics.map((t) => `
                    <span class="topic-tag" style="background:#DCFCE7; color:#166534;">
                        ${escapeHtml(t.topic)} — ${t.correct}/${t.total} (${t.pct}%)
                    </span>
                `).join("")}
            </div>
        </div>` : ""}

        <h3 style="margin-bottom:12px;">Quiz History</h3>
        <div class="dashboard-grid">
            ${state.quizHistory
                .map((item) => {
                    const badgeClass = item.score >= 80 ? "good" : item.score >= 50 ? "ok" : "poor";
                    return `
                        <div class="dashboard-card">
                            <div class="dashboard-card-header">
                                <div class="dashboard-card-icon">📄</div>
                                <div>
                                    <div class="dashboard-card-title">${escapeHtml(item.documentName)}</div>
                                    <div class="dashboard-card-meta">${new Date(item.date).toLocaleString()}</div>
                                </div>
                            </div>
                            <div class="dashboard-card-score">
                                <span>${item.correctCount}/${item.total} correct</span>
                                <span class="dashboard-score-badge ${badgeClass}">${item.score}%</span>
                            </div>
                        </div>
                    `;
                })
                .join("")}
        </div>
    `;
}


function confirmExit() {
    if (confirm("Exit quiz? Your current progress will be lost.")) {
        showPage("upload");
    }
}

function showError(message) {
    const errorEl = document.getElementById("error-message");
    errorEl.style.display = "flex";
    errorEl.textContent = message;
}

function hideError() {
    document.getElementById("error-message").style.display = "none";
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
function toggleTeacherMode() {
    const isTeacher = document.getElementById("teacher-toggle").checked;
    document.getElementById("teacher-controls").style.display = isTeacher ? "block" : "none";
    bindOptionGroup("teacher-count-options", () => {});
    bindOptionGroup("version-count-options", () => {});
}

async function generateTeacherQuiz() {
    if (!state.selectedFile) return;

    hideError();
    const questionCount = Number(document.querySelector("#teacher-count-options .selected")?.dataset.value || 10);
    const numVersions = Number(document.querySelector("#version-count-options .selected")?.dataset.value || 1);
    const easyPct = Number(document.getElementById("easy-pct").value);
    const mediumPct = Number(document.getElementById("medium-pct").value);
    const hardPct = Number(document.getElementById("hard-pct").value);

    if (easyPct + mediumPct + hardPct !== 100) {
        showError("Difficulty percentages must sum to 100.");
        return;
    }

    document.getElementById("teacher-generate-btn").disabled = true;
    document.getElementById("analyzing-title").textContent = "Generating teacher quiz...";
    document.getElementById("analyzing-subtitle").textContent = "Building question versions and answer keys";
    document.getElementById("analyzing-state").style.display = "block";
    renderSteps(["Reading PDF content", "Generating questions", "Building versions"], 1);

    const formData = new FormData();
    formData.append("file", state.selectedFile);
    formData.append("question_count", String(questionCount));
    formData.append("num_versions", String(numVersions));
    formData.append("easy_pct", String(easyPct));
    formData.append("medium_pct", String(mediumPct));
    formData.append("hard_pct", String(hardPct));

    try {
        const response = await fetch(`${API_BASE}/api/teacher-quiz`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Failed to generate teacher quiz.");
        }
        showTeacherQuiz(data);
    } catch (error) {
        showError(error.message || "Something went wrong generating the teacher quiz.");
    } finally {
        document.getElementById("analyzing-state").style.display = "none";
        document.getElementById("teacher-generate-btn").disabled = false;
    }
}

function showTeacherQuiz(data) {
    showPage("teacher-quiz");
    document.getElementById("teacher-quiz-doc-name").textContent = data.document_name || "Uploaded PDF";

    const versionEntries = Object.entries(data.versions);
    const letters = ["A", "B", "C", "D"];

    const versionsHtml = versionEntries.map(([label, questions]) => {
        const quizText = questions.map((q, i) =>
            `${i + 1}. ${q.question}\n` +
            q.options.map((opt, oi) => `   ${letters[oi]}) ${opt}`).join("\n")
        ).join("\n\n");

        const answerKeyText = questions.map((q, i) =>
            `${i + 1}. ${letters[q.correct_index]}`
        ).join("   ");

        const questionsHtml = questions.map((q, i) => `
            <div class="question-card" style="margin-bottom: 16px;">
                <div class="question-meta">
                    <span class="question-number">Q${i + 1}</span>
                    <span class="question-difficulty ${q.difficulty}">${q.difficulty}</span>
                </div>
                <div class="question-text">${escapeHtml(q.question)}</div>
                <div class="options">
                    ${q.options.map((opt, oi) => `
                        <div class="option ${oi === q.correct_index ? "correct" : ""}" style="cursor:default;">
                            <span class="option-letter">${letters[oi]}</span>
                            <span>${escapeHtml(opt)}</span>
                        </div>
                    `).join("")}
                </div>
            </div>
        `).join("");

        return `
            <div style="margin-bottom: 32px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <h2>Version ${label}</h2>
                    <button class="btn-secondary" onclick="copyQuizText('${label}')">📋 Copy for Google Forms</button>
                </div>
                <textarea id="quiz-text-${label}" style="display:none;">${escapeHtml(quizText)}\n\nAnswer Key: ${escapeHtml(answerKeyText)}</textarea>
                ${questionsHtml}
                <div class="topics-list">
                    <h3>Answer Key</h3>
                    <p style="font-family: monospace; font-size: 15px;">${escapeHtml(answerKeyText)}</p>
                </div>
            </div>
        `;
    }).join("<hr style='margin: 32px 0; border: none; border-top: 1px solid #E2E8F0;' />");

    document.getElementById("teacher-quiz-content").innerHTML = `
        <div class="setup-stats" style="margin-bottom: 24px;">
            <div class="setup-stat blue">
                <div class="setup-stat-label">Questions per Version</div>
                <div class="setup-stat-value">${data.question_count}</div>
            </div>
            <div class="setup-stat pink">
                <div class="setup-stat-label">Versions</div>
                <div class="setup-stat-value">${versionEntries.length}</div>
            </div>
            <div class="setup-stat orange">
                <div class="setup-stat-label">Mode</div>
                <div class="setup-stat-value" style="font-size:16px;">${data.ai_mode === "openai" ? "AI" : "Local"}</div>
            </div>
        </div>
        ${versionsHtml}
    `;
}

function copyQuizText(label) {
    const textarea = document.getElementById(`quiz-text-${label}`);
    textarea.style.display = "block";
    textarea.select();
    document.execCommand("copy");
    textarea.style.display = "none";
    alert(`Version ${label} copied — paste into Google Forms or a document.`);
}

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}