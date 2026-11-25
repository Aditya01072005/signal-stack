import React, { useState, useEffect, useCallback } from 'react';
import {
  Radar,
  TrendingUp,
  AlertTriangle,
  MinusCircle,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  Sparkles,
  RefreshCw,
  Search,
  CheckCircle2,
  X,
  Building2,
  Activity,
  Cpu,
  ArrowUpRight,
  Gauge,
  Flame,
  Award,
  Crosshair,
  Compass,
} from 'lucide-react';
import api from '../api/client';

export default function IntelligenceFeed({ selectedCompany }) {
  // Signals state
  const [signals, setSignals] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Analyzing state
  const [analyzingSignalId, setAnalyzingSignalId] = useState(null);
  const [isAnalyzingAll, setIsAnalyzingAll] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);

  // Filters
  const [classificationFilter, setClassificationFilter] = useState('all'); // 'all' | 'opportunity' | 'threat' | 'neutral' | 'pending'
  const [verificationFilter, setVerificationFilter] = useState('all'); // 'all' | 'verified' | 'unverified'
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch signals and ranked data, merging them by ID
  const loadSignalsData = useCallback(async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      // 1. Fetch raw recorded signals
      const rawRes = await api.signals.list(selectedCompany.id, { limit: 100 });
      const rawItems = rawRes?.items || (Array.isArray(rawRes) ? rawRes : []);

      // 2. Fetch ranked signals (already analyzed by Ollama)
      let rankedItems = [];
      try {
        const rankedRes = await api.signals.listRanked(selectedCompany.id, { limit: 100 });
        rankedItems = rankedRes?.items || (Array.isArray(rankedRes) ? rankedRes : []);
      } catch {
        // Silent fallback if no ranked signals yet
      }

      // Create a lookup map of analyzed signals
      const rankedMap = new Map();
      for (const item of rankedItems) {
        rankedMap.set(String(item.id), item);
      }

      // Merge: preserve all raw signals and augment with analyzed attributes
      const merged = rawItems.map((raw) => {
        const ranked = rankedMap.get(String(raw.id));
        if (ranked) {
          return {
            ...raw,
            ...ranked,
            is_analyzed: true,
          };
        }
        return {
          ...raw,
          is_analyzed: false,
          opportunity_threat: raw.opportunity_threat || 'pending',
        };
      });

      // Also include any ranked signals not present in rawItems
      for (const ranked of rankedItems) {
        if (!merged.some((m) => String(m.id) === String(ranked.id))) {
          merged.push({
            ...ranked,
            is_verified: true,
            is_analyzed: true,
          });
        }
      }

      // Sort by composite_rank (descending) or discovered_at (descending)
      merged.sort((a, b) => {
        const rankA = a.composite_rank ?? -1;
        const rankB = b.composite_rank ?? -1;
        if (rankB !== rankA) return rankB - rankA;
        return new Date(b.discovered_at || 0) - new Date(a.discovered_at || 0);
      });

      setSignals(merged);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load intelligence signals.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCompany]);

  useEffect(() => {
    loadSignalsData();
  }, [loadSignalsData]);

  // Run Monitoring to crawl sources & detect new signals
  const handleRunMonitoring = async () => {
    if (!selectedCompany?.id) return;

    setIsMonitoring(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.monitoring.trigger(selectedCompany.id);
      setSuccessMessage(
        `Monitoring cycle complete! Checked ${res.sources_checked} sources, found ${res.new_signals} new signals.`
      );
      await loadSignalsData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to execute monitoring cycle.');
    } finally {
      setIsMonitoring(false);
    }
  };

  // Analyze an individual signal using the backend API
  const handleAnalyzeSignal = async (signalId) => {
    if (!selectedCompany?.id || !signalId) return;

    setAnalyzingSignalId(signalId);
    setErrorMessage(null);
    try {
      const analyzed = await api.signals.analyze(selectedCompany.id, signalId);

      setSignals((prev) =>
        prev.map((s) =>
          String(s.id) === String(signalId)
            ? { ...s, ...analyzed, is_analyzed: true }
            : s
        )
      );
      setSuccessMessage(`Signal analyzed and classified as ${analyzed.opportunity_threat.toUpperCase()}.`);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to analyze signal with Ollama.');
    } finally {
      setAnalyzingSignalId(null);
    }
  };

  // Analyze all pending signals sequentially
  const handleAnalyzeAllPending = async () => {
    if (!selectedCompany?.id) return;
    const pendingList = signals.filter((s) => !s.is_analyzed || s.opportunity_threat === 'pending');
    if (pendingList.length === 0) return;

    setIsAnalyzingAll(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let completedCount = 0;
    try {
      for (const item of pendingList) {
        setAnalyzingSignalId(item.id);
        try {
          const analyzed = await api.signals.analyze(selectedCompany.id, item.id);
          setSignals((prev) =>
            prev.map((s) =>
              String(s.id) === String(item.id)
                ? { ...s, ...analyzed, is_analyzed: true }
                : s
            )
          );
          completedCount += 1;
        } catch (singleErr) {
          console.warn(`Failed to analyze signal ${item.id}:`, singleErr.message);
        }
      }
      setSuccessMessage(`Completed AI analysis for ${completedCount} pending signals.`);
    } catch (err) {
      setErrorMessage(err.message || 'Failed during batch signal analysis.');
    } finally {
      setIsAnalyzingAll(false);
      setAnalyzingSignalId(null);
    }
  };

  // Filter calculations
  const pendingCount = signals.filter((s) => !s.is_analyzed || s.opportunity_threat === 'pending').length;
  const oppCount = signals.filter((s) => s.opportunity_threat === 'opportunity').length;
  const threatCount = signals.filter((s) => s.opportunity_threat === 'threat').length;
  const neutralCount = signals.filter((s) => s.opportunity_threat === 'neutral').length;

  const filteredSignals = signals.filter((s) => {
    // Classification filter
    if (classificationFilter === 'opportunity' && s.opportunity_threat !== 'opportunity') return false;
    if (classificationFilter === 'threat' && s.opportunity_threat !== 'threat') return false;
    if (classificationFilter === 'neutral' && s.opportunity_threat !== 'neutral') return false;
    if (classificationFilter === 'pending' && (s.is_analyzed && s.opportunity_threat !== 'pending')) return false;

    // Verification filter
    if (verificationFilter === 'verified' && !s.is_verified) return false;
    if (verificationFilter === 'unverified' && s.is_verified) return false;

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = s.title?.toLowerCase().includes(q);
      const matchSnippet = s.content_snippet?.toLowerCase().includes(q);
      const matchUrl = s.source_url?.toLowerCase().includes(q);
      const matchArea = s.business_area?.toLowerCase().includes(q);
      if (!matchTitle && !matchSnippet && !matchUrl && !matchArea) return false;
    }

    return true;
  });

  // Empty state if no company selected
  if (!selectedCompany) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center max-w-xl mx-auto space-y-4">
        <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
          <Building2 className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-white tracking-tight">No Target Company Selected</h3>
        <p className="text-xs text-slate-400">
          Select a registered company from the header dropdown or the Company Setup page to inspect its real-time Intelligence Feed.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Top Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Radar className="w-6 h-6 text-indigo-400" />
            <span>Signal Radar & Intelligence Feed</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time market movement stream classified across Opportunity, Threat, and Neutral with AI scoring.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto">
          <button
            onClick={handleRunMonitoring}
            disabled={isMonitoring || isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow-md transition-all disabled:opacity-50"
            title="Crawl all registered sources to discover new signals"
          >
            <Activity className={`w-3.5 h-3.5 text-cyan-400 ${isMonitoring ? 'animate-spin' : ''}`} />
            <span>{isMonitoring ? 'Scanning Sources...' : 'Run Signal Discovery'}</span>
          </button>

          {pendingCount > 0 && (
            <button
              onClick={handleAnalyzeAllPending}
              disabled={isAnalyzingAll}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50"
            >
              <Cpu className={`w-3.5 h-3.5 ${isAnalyzingAll ? 'animate-spin text-cyan-300' : ''}`} />
              <span>{isAnalyzingAll ? 'Analyzing Batch...' : `Analyze ${pendingCount} Pending`}</span>
            </button>
          )}

          <button
            onClick={loadSignalsData}
            disabled={isLoading}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Refresh feed"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Total Signals</p>
            <p className="text-xl font-bold text-white mt-0.5">{signals.length}</p>
          </div>
          <Compass className="w-5 h-5 text-indigo-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-emerald-400 font-medium">Opportunities</p>
            <p className="text-xl font-bold text-emerald-300 mt-0.5">{oppCount}</p>
          </div>
          <TrendingUp className="w-5 h-5 text-emerald-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-rose-400 font-medium">Threats</p>
            <p className="text-xl font-bold text-rose-300 mt-0.5">{threatCount}</p>
          </div>
          <AlertTriangle className="w-5 h-5 text-rose-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-cyan-400 font-medium">Pending AI Analysis</p>
            <p className="text-xl font-bold text-cyan-300 mt-0.5">{pendingCount}</p>
          </div>
          <Cpu className="w-5 h-5 text-cyan-400" />
        </div>
      </div>

      {/* Alert Banners */}
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
              <span className="font-semibold block text-rose-200">Signal Engine Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4 space-y-3 shadow-xl">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Classification Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setClassificationFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                classificationFilter === 'all'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              All Signals ({signals.length})
            </button>
            <button
              onClick={() => setClassificationFilter('opportunity')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                classificationFilter === 'opportunity'
                  ? 'bg-emerald-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-emerald-300 border border-slate-800'
              }`}
            >
              Opportunities ({oppCount})
            </button>
            <button
              onClick={() => setClassificationFilter('threat')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                classificationFilter === 'threat'
                  ? 'bg-rose-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-rose-300 border border-slate-800'
              }`}
            >
              Threats ({threatCount})
            </button>
            <button
              onClick={() => setClassificationFilter('neutral')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                classificationFilter === 'neutral'
                  ? 'bg-slate-700 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              Neutral ({neutralCount})
            </button>
            <button
              onClick={() => setClassificationFilter('pending')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                classificationFilter === 'pending'
                  ? 'bg-cyan-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-cyan-300 border border-slate-800'
              }`}
            >
              Pending ({pendingCount})
            </button>
          </div>

          {/* Verification Dropdown & Search Bar */}
          <div className="flex items-center gap-2">
            <select
              value={verificationFilter}
              onChange={(e) => setVerificationFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="all">Verification: All</option>
              <option value="verified">Verified Evidence</option>
              <option value="unverified">Unverified Only</option>
            </select>

            <div className="relative min-w-[200px]">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search signals..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>
        </div>
      </div>

      {/* Signals Feed List */}
      <div className="space-y-4">
        {isLoading && signals.length === 0 ? (
          <div className="py-16 text-center text-xs text-slate-400 space-y-3">
            <RefreshCw className="w-6 h-6 mx-auto animate-spin text-indigo-400" />
            <p>Loading intelligence signals...</p>
          </div>
        ) : filteredSignals.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
              <Compass className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h4 className="text-base font-bold text-white tracking-tight">
                {signals.length === 0 ? 'No Signals Recorded Yet' : 'No Signals Match Current Filters'}
              </h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                {signals.length === 0
                  ? 'Run "Signal Discovery" to crawl company sources and identify changes, pricing updates, product pivots, or competitor activity.'
                  : 'Try clearing your search term or switching the classification filter.'}
              </p>
            </div>
            {signals.length === 0 && (
              <button
                onClick={handleRunMonitoring}
                disabled={isMonitoring}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition-all"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Run Signal Discovery Now</span>
              </button>
            )}
          </div>
        ) : (
          filteredSignals.map((sig) => {
            const isAnalyzed = Boolean(sig.is_analyzed || sig.ai_interpretation);
            const isAnalyzingThis = analyzingSignalId === sig.id;
            const oppThreat = (sig.opportunity_threat || 'pending').toLowerCase();

            // Date format
            const dateStr = sig.discovered_at || sig.published_at;
            const formattedDate = dateStr
              ? new Date(dateStr).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
              : 'Recent';

            return (
              <div
                key={sig.id}
                className={`rounded-2xl bg-slate-900 border transition-all p-5 shadow-xl space-y-4 group hover:border-slate-700 ${
                  oppThreat === 'opportunity'
                    ? 'border-emerald-950/80 hover:border-emerald-700/50'
                    : oppThreat === 'threat'
                    ? 'border-rose-950/80 hover:border-rose-700/50'
                    : 'border-slate-800'
                }`}
              >
                {/* Header Row: Classification Badge + Verification Badge + Date */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Classification Tag */}
                    {oppThreat === 'opportunity' && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800">
                        <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Opportunity</span>
                      </span>
                    )}
                    {oppThreat === 'threat' && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-950/80 text-rose-300 border border-rose-800">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                        <span>Threat</span>
                      </span>
                    )}
                    {oppThreat === 'neutral' && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
                        <MinusCircle className="w-3.5 h-3.5 text-slate-400" />
                        <span>Neutral</span>
                      </span>
                    )}
                    {oppThreat === 'pending' && (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-950/80 text-indigo-300 border border-indigo-800">
                        <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Pending Analysis</span>
                      </span>
                    )}

                    {/* Verification Badge */}
                    {sig.is_verified ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-950/40 text-emerald-400 border border-emerald-900/60">
                        <ShieldCheck className="w-3 h-3 text-emerald-400" />
                        <span>Verified Evidence</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                        <ShieldAlert className="w-3 h-3 text-slate-500" />
                        <span>Unverified</span>
                      </span>
                    )}

                    {/* Business Area / Development Type */}
                    {sig.business_area && (
                      <span className="text-[11px] font-medium text-slate-300 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
                        {sig.business_area}
                      </span>
                    )}
                  </div>

                  {/* Date & Source URL */}
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{formattedDate}</span>
                    {sig.source_url?.startsWith('internal-document://') ? (
                      <span
                        title={sig.source_url}
                        className="inline-flex max-w-[220px] truncate text-cyan-400"
                      >
                        Internal document evidence · {sig.source_url.slice(20)}
                      </span>
                    ) : sig.source_url && /^https?:\/\//i.test(sig.source_url) ? (
                      <a
                        href={sig.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-indigo-400 hover:text-cyan-300 hover:underline max-w-[220px] truncate"
                      >
                        <span className="truncate">{sig.source_url}</span>
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      </a>
                    ) : sig.source_url ? (
                      <span className="text-slate-500">Stored evidence</span>
                    ) : null}
                  </div>
                </div>

                {/* Title & Summary */}
                <div className="space-y-1.5">
                  <h3 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors tracking-tight">
                    {sig.title}
                  </h3>
                  <p className="text-xs md:text-sm text-slate-300 leading-relaxed">
                    {sig.content_snippet}
                  </p>
                </div>

                {/* Verbatim Excerpt (if verified) */}
                {sig.verbatim_quote && (
                  <div className="p-3 rounded-xl bg-slate-950/80 border-l-2 border-emerald-500 border-r border-t border-b border-slate-800/80">
                    <p className="text-xs text-slate-400 font-mono italic">
                      "{sig.verbatim_quote}"
                    </p>
                  </div>
                )}

                {/* Multi-Dimensional Scoring Grid (Impact, Urgency, Credibility, Relevance) */}
                {isAnalyzed && (
                  <div className="pt-2 border-t border-slate-800/80 space-y-3">
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-xs">
                      {/* Impact */}
                      <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-slate-400">
                          <Flame className="w-3.5 h-3.5 text-amber-400" />
                          <span>Impact</span>
                        </div>
                        <span className="font-bold text-slate-100">
                          {sig.business_impact_score ? Number(sig.business_impact_score).toFixed(1) : '—'}
                          <span className="text-[10px] text-slate-500 font-normal">/10</span>
                        </span>
                      </div>

                      {/* Urgency */}
                      <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-slate-400">
                          <Gauge className="w-3.5 h-3.5 text-rose-400" />
                          <span>Urgency</span>
                        </div>
                        <span className="font-bold text-slate-100">
                          {sig.urgency_score ? Number(sig.urgency_score).toFixed(1) : '—'}
                          <span className="text-[10px] text-slate-500 font-normal">/10</span>
                        </span>
                      </div>

                      {/* Credibility */}
                      <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-slate-400">
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Credibility</span>
                        </div>
                        <span className="font-bold text-slate-100">
                          {sig.credibility_score ? Number(sig.credibility_score).toFixed(1) : '—'}
                          <span className="text-[10px] text-slate-500 font-normal">/10</span>
                        </span>
                      </div>

                      {/* Relevance */}
                      <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-slate-400">
                          <Crosshair className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Relevance</span>
                        </div>
                        <span className="font-bold text-slate-100">
                          {sig.relevance_score ? Number(sig.relevance_score).toFixed(1) : '—'}
                          <span className="text-[10px] text-slate-500 font-normal">/10</span>
                        </span>
                      </div>

                      {/* Composite Rank */}
                      <div className="p-2.5 rounded-lg bg-indigo-950/50 border border-indigo-800/60 flex items-center justify-between col-span-2 sm:col-span-1">
                        <div className="flex items-center gap-1.5 text-indigo-300 font-semibold">
                          <Award className="w-3.5 h-3.5 text-indigo-400" />
                          <span>Rank</span>
                        </div>
                        <span className="font-bold text-cyan-300">
                          {sig.composite_rank ? Number(sig.composite_rank).toFixed(1) : '—'}
                          <span className="text-[10px] text-indigo-400 font-normal">/10</span>
                        </span>
                      </div>
                    </div>

                    {/* AI Strategic Interpretation & Recommended Action */}
                    {(sig.ai_interpretation || sig.recommended_action) && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                        {sig.ai_interpretation && (
                          <div className="p-3 rounded-xl bg-slate-950/90 border border-slate-800/80 space-y-1">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400 flex items-center gap-1">
                              <Sparkles className="w-3 h-3" /> Strategic AI Interpretation
                            </span>
                            <p className="text-xs text-slate-300 leading-relaxed">
                              {sig.ai_interpretation}
                            </p>
                          </div>
                        )}

                        {sig.recommended_action && (
                          <div className="p-3 rounded-xl bg-slate-950/90 border border-slate-800/80 space-y-1">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-emerald-400 flex items-center gap-1">
                              <ArrowUpRight className="w-3 h-3" /> Recommended Action
                            </span>
                            <p className="text-xs text-slate-300 leading-relaxed">
                              {sig.recommended_action}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Pending Analysis Action Footer */}
                {!isAnalyzed && (
                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
                    <span className="text-xs text-slate-400">
                      Unscored raw signal from web monitoring pipeline
                    </span>

                    <button
                      onClick={() => handleAnalyzeSignal(sig.id)}
                      disabled={isAnalyzingThis}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-50"
                    >
                      {isAnalyzingThis ? (
                        <>
                          <RefreshCw className="w-3 h-3 animate-spin text-cyan-300" />
                          <span>Classifying with Ollama...</span>
                        </>
                      ) : (
                        <>
                          <Cpu className="w-3 h-3" />
                          <span>Analyze Signal</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
