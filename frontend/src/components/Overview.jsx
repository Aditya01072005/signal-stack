import React, { useState, useEffect, useCallback } from 'react';
import {
  Building2,
  MessageSquareText,
  Radio,
  Radar,
  FileText,
  Clock,
  Sparkles,
  ArrowRight,
  Users2,
  RefreshCw,
} from 'lucide-react';
import api from '../api/client';

/* eslint-disable react/set-state-in-effect */

export default function Overview({ onNavigate, backendStatus, selectedCompany, companies = [] }) {
  // Real live metrics from backend
  const [stats, setStats] = useState({
    companiesCount: companies.length,
    sourcesCount: 0,
    signalsCount: 0,
    competitorsCount: 0,
    briefsCount: 0,
    schedulerRunning: false,
    schedulerTimezone: 'UTC',
    nextBriefRun: null,
  });
  const [isLoadingStats, setIsLoadingStats] = useState(false);

  // Load real metrics
  const loadDashboardStats = useCallback(async () => {
    setIsLoadingStats(true);
    try {
      // 1. Scheduler status
      let schedRunning = false;
      let schedTz = 'UTC';
      let nextRun = null;
      try {
        const sched = await api.scheduler.getStatus();
        schedRunning = Boolean(sched?.is_running);
        schedTz = sched?.timezone || 'UTC';
        const weeklyJob = sched?.jobs?.find((j) => j.id === 'weekly_brief_job');
        if (weeklyJob?.next_run_time) {
          nextRun = new Date(weeklyJob.next_run_time).toLocaleDateString(undefined, {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          });
        }
      } catch {
        // Scheduler offline fallback
      }

      // 2. Counts for active company if available
      let sourcesCount = 0;
      let signalsCount = 0;
      let competitorsCount = 0;
      let briefsCount = 0;

      if (selectedCompany?.id) {
        try {
          const [srcRes, sigRes, compRes, briefRes] = await Promise.allSettled([
            api.sources.list(selectedCompany.id, { include_inactive: true, limit: 1 }),
            api.signals.list(selectedCompany.id, { limit: 1 }),
            api.competitors.list(selectedCompany.id, { include_inactive: true }),
            api.briefs.list(selectedCompany.id, { limit: 1 }),
          ]);

          if (srcRes.status === 'fulfilled') {
            sourcesCount = srcRes.value?.total ?? (Array.isArray(srcRes.value) ? srcRes.value.length : 0);
          }
          if (sigRes.status === 'fulfilled') {
            signalsCount = sigRes.value?.total ?? (Array.isArray(sigRes.value) ? sigRes.value.length : 0);
          }
          if (compRes.status === 'fulfilled') {
            competitorsCount = Array.isArray(compRes.value) ? compRes.value.length : (compRes.value?.total ?? 0);
          }
          if (briefRes.status === 'fulfilled') {
            briefsCount = briefRes.value?.total ?? (Array.isArray(briefRes.value) ? briefRes.value.length : 0);
          }
        } catch {
          // Silent fallback
        }
      }

      setStats({
        companiesCount: companies.length,
        sourcesCount,
        signalsCount,
        competitorsCount,
        briefsCount,
        schedulerRunning: schedRunning,
        schedulerTimezone: schedTz,
        nextBriefRun: nextRun,
      });
    } finally {
      setIsLoadingStats(false);
    }
  }, [companies.length, selectedCompany]);

  useEffect(() => {
    loadDashboardStats();
  }, [loadDashboardStats]);

  const PIPELINE_STEPS = [
    {
      title: 'Company Setup & Research',
      desc: 'Normalized website crawl, metadata extraction, and Fact vs Assumption intelligence profile.',
      icon: Building2,
      tab: 'companies',
      tag: '1. Onboarding',
    },
    {
      title: 'Competitor Intelligence',
      desc: '3-tier competitor mapping (Direct, Indirect, Substitute) with evidence citation and AI discovery.',
      icon: Users2,
      tab: 'competitors',
      tag: '2. Competitors',
    },
    {
      title: 'Adaptive AI Founder Interview',
      desc: '10-question dynamic strategic interview powered by local Ollama with stateful context memory.',
      icon: MessageSquareText,
      tab: 'interview',
      tag: '3. Founder Context',
    },
    {
      title: 'Ethical Web Sources',
      desc: 'Monitored target domains with strict robots.txt compliance, rate-limiting, and crawl health scoring.',
      icon: Radio,
      tab: 'sources',
      tag: '4. Sources',
    },
    {
      title: 'Signal Radar & Feed',
      desc: 'Automated delta-checking across competitor pricing, hiring, and product shifts with AI scoring.',
      icon: Radar,
      tab: 'signals',
      tag: '5. Signals',
    },
    {
      title: 'Monday Morning Briefs',
      desc: '10-section executive briefing synthesizing competitor signals and founder interview answers.',
      icon: FileText,
      tab: 'briefs',
      tag: '6. Synthesis',
    },
  ];

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Hero Welcome Masthead */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 p-6 md:p-8 shadow-2xl">
        <div className="relative z-10 max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-xs font-semibold text-indigo-400">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Autonomous Intelligence & Executive Briefing Engine</span>
          </div>

          <h2 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight leading-tight">
            Signal Stack — Executive Decision Intelligence
          </h2>

          <p className="text-slate-300 text-sm md:text-base leading-relaxed">
            Continuously monitors market movements, analyzes competitor positioning,
            and synthesizes raw intelligence into strategic Monday Morning Briefs using local,
            private LLM inference.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            <button
              onClick={() => onNavigate('companies')}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-lg shadow-indigo-600/30 transition-all hover:translate-x-0.5"
            >
              <span>{selectedCompany ? 'Manage Target Company' : 'Register Target Company'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => onNavigate('briefs')}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-sm font-medium transition-all"
            >
              <FileText className="w-4 h-4 text-cyan-400" />
              <span>Open Executive Briefs</span>
            </button>
          </div>
        </div>

        {/* Decorative Grid Accent */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-radial from-indigo-500/10 to-transparent pointer-events-none" />
      </div>

      {/* Real Live Backend Metrics Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Live System Telemetry
            </h3>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                backendStatus === 'online'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  backendStatus === 'online' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
                }`}
              />
              <span>{backendStatus === 'online' ? 'Connected' : 'Offline'}</span>
            </span>
          </div>

          <button
            onClick={loadDashboardStats}
            disabled={isLoadingStats}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-50"
            title="Refresh live metrics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingStats ? 'animate-spin text-indigo-400' : ''}`} />
            <span className="hidden sm:inline">Refresh Stats</span>
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Companies Count */}
        <div
          onClick={() => onNavigate('companies')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-indigo-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-400">Companies</p>
            <Building2 className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-xl font-bold text-white mt-1.5">{companies.length}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Registered targets</p>
        </div>

        {/* Competitors Count */}
        <div
          onClick={() => onNavigate('competitors')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-rose-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-rose-400">Competitors</p>
            <Users2 className="w-4 h-4 text-rose-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-xl font-bold text-white mt-1.5">{stats.competitorsCount}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">3-tier mapped</p>
        </div>

        {/* Sources Count */}
        <div
          onClick={() => onNavigate('sources')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-cyan-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-cyan-400">Sources</p>
            <Radio className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-xl font-bold text-white mt-1.5">{stats.sourcesCount}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Monitored domains</p>
        </div>

        {/* Signals Count */}
        <div
          onClick={() => onNavigate('signals')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-emerald-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-emerald-400">Signals</p>
            <Radar className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-xl font-bold text-white mt-1.5">{stats.signalsCount}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Recorded deltas</p>
        </div>

        {/* Briefs Count */}
        <div
          onClick={() => onNavigate('briefs')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-violet-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-violet-400">Briefs</p>
            <FileText className="w-4 h-4 text-violet-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-xl font-bold text-white mt-1.5">{stats.briefsCount}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">10-section reports</p>
        </div>

        {/* Scheduler Status */}
        <div
          onClick={() => onNavigate('scheduler')}
          className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-amber-500/50 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <p className="text-xs text-amber-400">Scheduler</p>
            <Clock className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
          </div>
          <p className="text-sm font-bold text-white mt-1.5 flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                stats.schedulerRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'
              }`}
            />
            <span>{stats.schedulerRunning ? 'Active' : 'Paused'}</span>
          </p>
          <p className="text-[10px] text-slate-500 mt-0.5 font-mono truncate">
            {stats.nextBriefRun ? `Next: ${stats.nextBriefRun}` : `${stats.schedulerTimezone} daemon`}
          </p>
        </div>
      </div>
      </div>

      {/* Target Company Status Card (if selected) */}
      {selectedCompany && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-cyan-950/60 px-2.5 py-0.5 rounded-full border border-cyan-800">
                Active Intelligence Scope
              </span>
              <span className="text-xs text-slate-400">•</span>
              <span className="text-xs text-slate-400">{selectedCompany.industry || 'Enterprise'}</span>
            </div>
            <h3 className="text-xl font-bold text-white tracking-tight">
              {selectedCompany.name}
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              {selectedCompany.website_url}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => onNavigate('interview')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-colors"
            >
              <MessageSquareText className="w-3.5 h-3.5 text-indigo-400" />
              <span>Adaptive Interview</span>
            </button>
            <button
              onClick={() => onNavigate('signals')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition-colors"
            >
              <Radar className="w-3.5 h-3.5 text-emerald-400" />
              <span>Signal Radar</span>
            </button>
            <button
              onClick={() => onNavigate('briefs')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Generate Brief</span>
            </button>
          </div>
        </div>
      )}

      {/* Autonomous Pipeline Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-white tracking-tight">
            Autonomous Pipeline Capabilities
          </h3>
          <span className="text-xs text-slate-400">
            Click any module to jump directly to its active workspace
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {PIPELINE_STEPS.map((step, idx) => {
            const StepIcon = step.icon;
            return (
              <div
                key={idx}
                onClick={() => onNavigate(step.tab)}
                className="p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-slate-700 hover:bg-slate-800/40 transition-all cursor-pointer group flex flex-col justify-between space-y-4 shadow-xl"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-9 h-9 rounded-xl bg-slate-800 flex items-center justify-center text-indigo-400 group-hover:text-cyan-400 transition-colors">
                      <StepIcon className="w-5 h-5" />
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700">
                      {step.tag}
                    </span>
                  </div>

                  <h4 className="text-sm font-bold text-white group-hover:text-indigo-300 transition-colors">
                    {step.title}
                  </h4>
                  <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                    {step.desc}
                  </p>
                </div>

                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-indigo-400 font-semibold group-hover:translate-x-0.5 transition-transform">
                  <span>Open Module</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
