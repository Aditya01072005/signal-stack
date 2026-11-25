import React, { useState, useEffect, useCallback } from 'react';
import {
  MessageSquareText,
  Sparkles,
  Send,
  SkipForward,
  Edit3,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Building2,
  History,
  Check,
  X,
  Cpu,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import api from '../api/client';

const MAX_QUESTIONS = 10;

export default function AdaptiveInterview({ selectedCompany, onNavigate }) {
  // Interview state
  const [activeInterview, setActiveInterview] = useState(null);
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [allQuestions, setAllQuestions] = useState([]);
  const [isComplete, setIsComplete] = useState(false);
  const [interviewStatus, setInterviewStatus] = useState('idle'); // 'idle' | 'in_progress' | 'completed'

  // Loading & Error States
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Form input for answering current question
  const [answerInput, setAnswerInput] = useState('');

  // Editing state for previously answered questions
  const [editingQuestionId, setEditingQuestionId] = useState(null);
  const [editText, setEditText] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // History panel toggle
  const [showHistory, setShowHistory] = useState(true);

  // Load active interview for selected company
  const loadInterviewData = useCallback(async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      // 1. Try to fetch the active interview
      try {
        const nextQRes = await api.interview.getActive(selectedCompany.id);
        if (nextQRes && nextQRes.interview_id) {
          // Fetch full interview with all questions
          const fullRes = await api.interview.getInterview(selectedCompany.id, nextQRes.interview_id);
          setActiveInterview(fullRes);
          setAllQuestions(fullRes.questions || []);
          setCurrentQuestion(nextQRes.current_question || null);
          setIsComplete(Boolean(nextQRes.is_complete || fullRes.status === 'completed'));
          setInterviewStatus(fullRes.status);
          setAnswerInput('');
          return;
        }
      } catch (err) {
        // HTTP 404 means no active interview
        if (err.status !== 404) {
          throw err;
        }
      }

      // 2. If no active interview, check if there's any completed interview in history
      const list = await api.interview.list(selectedCompany.id);
      if (Array.isArray(list) && list.length > 0) {
        const latest = list[0];
        setActiveInterview(latest);
        setAllQuestions(latest.questions || []);
        setCurrentQuestion(null);
        setIsComplete(latest.status === 'completed');
        setInterviewStatus(latest.status);
      } else {
        // No interview ever started
        setActiveInterview(null);
        setAllQuestions([]);
        setCurrentQuestion(null);
        setIsComplete(false);
        setInterviewStatus('idle');
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load interview state.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCompany]);

  useEffect(() => {
    loadInterviewData();
  }, [loadInterviewData]);

  // Start a new interview
  const handleStartInterview = async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.interview.start(selectedCompany.id);
      setActiveInterview(res.interview);
      setCurrentQuestion(res.current_question);
      setAllQuestions(res.interview.questions || [res.current_question]);
      setIsComplete(false);
      setInterviewStatus('in_progress');
      setAnswerInput('');
      setSuccessMessage('Interview session started. First adaptive question generated!');
    } catch (err) {
      setErrorMessage(err.message || 'Failed to start interview.');
    } finally {
      setIsLoading(false);
    }
  };

  // Submit answer for the current question
  const handleSubmitAnswer = async () => {
    if (!selectedCompany?.id || !activeInterview?.id) return;
    const answer = answerInput.trim();
    if (!answer) {
      setErrorMessage('Please type an answer or click "Skip Question".');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.interview.submitAnswer(selectedCompany.id, activeInterview.id, {
        answer,
        skip: false,
      });

      // Update question in state
      setAllQuestions((prev) => {
        const index = prev.findIndex((q) => q.id === res.question.id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = res.question;
          if (res.next_question) {
            updated.push(res.next_question);
          }
          return updated;
        }
        return [...prev, res.question, ...(res.next_question ? [res.next_question] : [])];
      });

      setCurrentQuestion(res.next_question || null);
      setInterviewStatus(res.interview_status);
      setIsComplete(Boolean(res.is_complete || res.interview_status === 'completed'));
      setAnswerInput('');

      if (res.is_complete) {
        setSuccessMessage('All 10 questions completed! Profile assumptions have been updated.');
      } else if (res.profile_updated) {
        setSuccessMessage('Answer saved and profile assumptions updated.');
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to submit answer.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Skip the current question
  const handleSkipQuestion = async () => {
    if (!selectedCompany?.id || !activeInterview?.id) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.interview.submitAnswer(selectedCompany.id, activeInterview.id, {
        skip: true,
      });

      setAllQuestions((prev) => {
        const index = prev.findIndex((q) => q.id === res.question.id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = res.question;
          if (res.next_question) updated.push(res.next_question);
          return updated;
        }
        return [...prev, res.question, ...(res.next_question ? [res.next_question] : [])];
      });

      setCurrentQuestion(res.next_question || null);
      setInterviewStatus(res.interview_status);
      setIsComplete(Boolean(res.is_complete || res.interview_status === 'completed'));
      setAnswerInput('');
    } catch (err) {
      setErrorMessage(err.message || 'Failed to skip question.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Save an edited answer
  const handleSaveEdit = async (questionId) => {
    if (!selectedCompany?.id || !activeInterview?.id) return;
    const answer = editText.trim();
    if (!answer) {
      setErrorMessage('Revised answer cannot be blank.');
      return;
    }

    setIsSavingEdit(true);
    setErrorMessage(null);
    try {
      const updatedQ = await api.interview.editAnswer(
        selectedCompany.id,
        activeInterview.id,
        questionId,
        { answer }
      );

      setAllQuestions((prev) =>
        prev.map((q) => (q.id === questionId ? updatedQ : q))
      );
      setEditingQuestionId(null);
      setEditText('');
      setSuccessMessage('Answer revised successfully.');
    } catch (err) {
      setErrorMessage(err.message || 'Failed to save revised answer.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Calculate answered count
  const answeredCount = allQuestions.filter((q) => q.user_answer !== null || q.is_skipped).length;
  const progressPercent = Math.min(100, Math.round((answeredCount / MAX_QUESTIONS) * 100));

  // If no company selected
  if (!selectedCompany) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center max-w-xl mx-auto space-y-4">
        <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
          <Building2 className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-white tracking-tight">No Target Company Selected</h3>
        <p className="text-xs text-slate-400">
          Please select a registered company from the header dropdown or the Company Setup page to conduct the adaptive AI interview.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <MessageSquareText className="w-6 h-6 text-indigo-400" />
            <span>Adaptive AI Founder Interview</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Dynamic 10-question strategic interview powered by <span className="text-slate-300 font-mono">llama3.2:3b</span> with stateful context memory.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start md:self-auto">
          <div className="bg-slate-900 border border-slate-800 px-3.5 py-1.5 rounded-xl flex items-center gap-2">
            <span className="text-xs text-slate-400">Target:</span>
            <span className="text-xs font-semibold text-cyan-400 truncate max-w-[160px]">
              {selectedCompany.name}
            </span>
          </div>

          <button
            onClick={loadInterviewData}
            disabled={isLoading}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Refresh interview status"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Progress & Status Card */}
      {activeInterview && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 shadow-xl space-y-3">
          <div className="flex items-center justify-between text-xs font-medium">
            <div className="flex items-center gap-2">
              <span className="text-slate-300">
                Question <strong className="text-white">{Math.min(answeredCount + (currentQuestion ? 1 : 0), MAX_QUESTIONS)}</strong> of {MAX_QUESTIONS}
              </span>
              <span className="text-slate-500">•</span>
              <span className="text-emerald-400">{answeredCount} Answered/Skipped</span>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${
                  isComplete
                    ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                    : 'bg-indigo-950/60 text-indigo-300 border-indigo-800'
                }`}
              >
                {isComplete ? 'Completed' : 'In Progress'}
              </span>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
            <div
              className="bg-gradient-to-r from-indigo-500 to-cyan-400 h-2 rounded-full transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* Alerts */}
      {successMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-800/80 text-xs text-emerald-300 flex items-center justify-between gap-2 shadow-lg">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-xs text-rose-300 flex items-start justify-between gap-2 shadow-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block text-rose-200">Interview API Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* VIEW 1: Idle (No Interview Started Yet) */}
      {interviewStatus === 'idle' && (
        <div className="rounded-2xl bg-gradient-to-br from-slate-900 via-indigo-950/30 to-slate-900 border border-slate-800 p-8 md:p-12 text-center space-y-6 shadow-2xl">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-inner">
            <Sparkles className="w-8 h-8 animate-pulse text-cyan-400" />
          </div>

          <div className="max-w-xl mx-auto space-y-2">
            <h3 className="text-2xl font-bold text-white tracking-tight">
              Begin Strategic Intelligence Interview
            </h3>
            <p className="text-sm text-slate-300 leading-relaxed">
              The AI interviewer generates targeted questions tailored to{' '}
              <strong className="text-white">{selectedCompany.name}</strong>. Answers are synthesized
              into founder context, sharpening weekly executive briefs and opportunity radar.
            </p>
          </div>

          <div className="pt-2 flex justify-center">
            <button
              onClick={handleStartInterview}
              disabled={isLoading}
              className="inline-flex items-center gap-2.5 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-xl shadow-indigo-600/30 transition-all hover:scale-105 disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-cyan-300" />
                  <span>Prompting Ollama & Generating Question 1...</span>
                </>
              ) : (
                <>
                  <MessageSquareText className="w-4 h-4 text-cyan-300" />
                  <span>Start Interview Session</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* VIEW 2: In-Progress Active Question Card */}
      {interviewStatus === 'in_progress' && currentQuestion && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 md:p-8 shadow-2xl space-y-6 relative overflow-hidden">
          {/* Question Meta Header */}
          <div className="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Question {currentQuestion.question_number} of {MAX_QUESTIONS}
              </span>
              {currentQuestion.is_follow_up && (
                <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-cyan-950/80 text-cyan-300 border border-cyan-800">
                  Follow-up Deep Dive
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span>Ollama llama3.2:3b</span>
            </div>
          </div>

          {/* Question Text */}
          <div className="space-y-2">
            <p className="text-lg md:text-xl font-semibold text-white leading-relaxed tracking-tight">
              {currentQuestion.question_text}
            </p>
            <p className="text-xs text-slate-400">
              Provide as much operational or strategic context as you wish. Answers enrich the executive intelligence profile.
            </p>
          </div>

          {/* Answer Input Area */}
          <div className="space-y-3">
            <textarea
              rows={4}
              value={answerInput}
              onChange={(e) => setAnswerInput(e.target.value)}
              placeholder="Type your response here..."
              disabled={isSubmitting}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all resize-y disabled:opacity-50"
            />

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-1">
              <button
                type="button"
                onClick={handleSkipQuestion}
                disabled={isSubmitting}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
              >
                <SkipForward className="w-4 h-4" />
                <span>Skip Question (Confidential / N/A)</span>
              </button>

              <button
                type="button"
                onClick={handleSubmitAnswer}
                disabled={isSubmitting || !answerInput.trim()}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02]"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-cyan-300" />
                    <span>Synthesizing Context & Next Question...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Submit Answer</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 3: Completed Session Review */}
      {isComplete && (
        <div className="rounded-2xl bg-gradient-to-br from-slate-900 via-emerald-950/20 to-slate-900 border border-slate-800 p-8 text-center space-y-4 shadow-xl">
          <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <h3 className="text-xl font-bold text-white tracking-tight">
              Adaptive Interview Complete
            </h3>
            <p className="text-xs text-slate-300 max-w-lg mx-auto">
              All questions have been answered or skipped. The AI has synthesized your responses into the company's intelligence baseline.
            </p>
          </div>

          <div className="pt-2 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={() => onNavigate && onNavigate('companies')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition-all"
            >
              <Building2 className="w-3.5 h-3.5" />
              <span>View Research Profile</span>
            </button>
            <button
              onClick={handleStartInterview}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
              <span>Start New Interview Session</span>
            </button>
          </div>
        </div>
      )}

      {/* QUESTION HISTORY & EDITABLE ANSWERS SECTION */}
      {allQuestions.length > 0 && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden">
          {/* Header Toggle */}
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full flex items-center justify-between p-5 text-left border-b border-slate-800/80 hover:bg-slate-800/30 transition-colors"
          >
            <div className="flex items-center gap-2.5">
              <History className="w-4 h-4 text-indigo-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Interview Transcript & Editable Answers
              </h3>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-semibold">
                {allQuestions.filter((q) => q.user_answer !== null || q.is_skipped).length}
              </span>
            </div>

            <div className="text-slate-400">
              {showHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </button>

          {/* Questions Accordion / List */}
          {showHistory && (
            <div className="p-5 space-y-4 max-h-[500px] overflow-y-auto">
              {allQuestions
                .filter((q) => q.user_answer !== null || q.is_skipped)
                .map((q) => {
                  const isEditing = editingQuestionId === q.id;

                  return (
                    <div
                      key={q.id}
                      className="p-4 rounded-xl bg-slate-950/70 border border-slate-800/90 space-y-3"
                    >
                      {/* Item Header */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-400">
                            Q{q.question_number}
                          </span>
                          {q.is_skipped ? (
                            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800">
                              Skipped
                            </span>
                          ) : (
                            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800">
                              Answered
                            </span>
                          )}
                          {q.is_edited && (
                            <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-800">
                              Edited
                            </span>
                          )}
                        </div>

                        {!isEditing && (
                          <button
                            onClick={() => {
                              setEditingQuestionId(q.id);
                              setEditText(q.user_answer || '');
                            }}
                            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-400 font-medium transition-colors"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                            <span>Edit Answer</span>
                          </button>
                        )}
                      </div>

                      {/* Question Text */}
                      <p className="text-sm font-medium text-slate-200">
                        {q.question_text}
                      </p>

                      {/* Answer or Edit Form */}
                      {isEditing ? (
                        <div className="space-y-2 pt-1">
                          <textarea
                            rows={3}
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            placeholder="Revise your answer..."
                            disabled={isSavingEdit}
                            className="w-full bg-slate-900 border border-indigo-500/60 rounded-lg p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => {
                                setEditingQuestionId(null);
                                setEditText('');
                              }}
                              disabled={isSavingEdit}
                              className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-white"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleSaveEdit(q.id)}
                              disabled={isSavingEdit || !editText.trim()}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow disabled:opacity-50"
                            >
                              {isSavingEdit ? (
                                <RefreshCw className="w-3 h-3 animate-spin" />
                              ) : (
                                <Check className="w-3 h-3" />
                              )}
                              <span>Save Revision</span>
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
                          {q.is_skipped ? (
                            <p className="text-xs text-slate-500 italic">
                              This question was skipped by the user.
                            </p>
                          ) : (
                            <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
                              {q.user_answer}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
