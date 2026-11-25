import React, { useState, useEffect, useCallback } from 'react';
import {
  Clock,
  Cpu,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertTriangle,
  Server,
  Activity,
  X,
  ShieldCheck,
} from 'lucide-react';
import api from '../api/client';

export default function SchedulerHealth({ backendStatus, onRefreshHealth }) {
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunningJob, setIsRunningJob] = useState(null); // 'briefs' | 'audit' | null
  const [errorMessage, setErrorMessage] = useState(null);
  const [jobResult, setJobResult] = useState(null);

  // Load scheduler status
  const loadStatusData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      try {
        const schedRes = await api.scheduler.getStatus();
        setSchedulerStatus(schedRes);
      } catch (err) {
        console.warn('Scheduler status call failed:', err.message);
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load system health status.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatusData();
  }, [loadStatusData]);

  // Run Weekly Brief Job Manually
  const handleRunWeeklyBriefs = async () => {
    setIsRunningJob('briefs');
    setErrorMessage(null);
    setJobResult(null);
    try {
      const res = await api.scheduler.runWeeklyBriefs();
      setJobResult({
        type: 'Weekly Brief Generation',
        ...res,
      });
      await loadStatusData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to execute weekly briefs scheduler job.');
    } finally {
      setIsRunningJob(null);
    }
  };

  // Run Monthly Source Health Audit Job Manually
  const handleRunSourceAudit = async () => {
    setIsRunningJob('audit');
    setErrorMessage(null);
    setJobResult(null);
    try {
      const res = await api.scheduler.runMonthlySourceHealthAudit();
      setJobResult({
        type: 'Monthly Source Health Audit',
        ...res,
      });
      await loadStatusData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to execute monthly source health audit job.');
    } finally {
      setIsRunningJob(null);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Clock className="w-6 h-6 text-indigo-400" />
            <span>Scheduler Automation & System Health</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time status of APScheduler background daemon, configured cron triggers, and database connectivity.
          </p>
        </div>

        <button
          onClick={() => {
            loadStatusData();
            if (onRefreshHealth) onRefreshHealth();
          }}
          disabled={isLoading}
          className="self-start md:self-auto inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
          <span>Refresh Engine Status</span>
        </button>
      </div>

      {/* Alert Notices */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-xs text-rose-300 flex items-start justify-between gap-2 shadow-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block text-rose-200">Scheduler API Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Job Execution Outcome Banner */}
      {jobResult && (
        <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-800 text-xs text-emerald-300 shadow-xl space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-bold uppercase tracking-wider text-[11px] flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>Job Execution Completed: {jobResult.type}</span>
            </span>
            <button onClick={() => setJobResult(null)} className="text-slate-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-[11px] text-slate-300">
            <div>Status: <strong className="text-emerald-400">{jobResult.status}</strong></div>
            <div>Companies: <strong>{jobResult.companies_total}</strong></div>
            <div>Succeeded: <strong className="text-emerald-400">{jobResult.succeeded}</strong></div>
            <div>Duration: <strong>{jobResult.duration_ms} ms</strong></div>
          </div>
        </div>
      )}

      {/* Status Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* APScheduler Status */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              APScheduler Daemon
            </span>
            <Clock className="w-4 h-4 text-indigo-400" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  schedulerStatus?.is_running ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
                }`}
              />
              <span className="text-lg font-bold text-white">
                {schedulerStatus?.is_running ? 'Running & Active' : 'Scheduler Paused'}
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Timezone: {schedulerStatus?.timezone || 'UTC'}
            </p>
          </div>
        </div>

        {/* Backend API Health */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              FastAPI Health
            </span>
            <Server className="w-4 h-4 text-cyan-400" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  backendStatus === 'online' ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <span className="text-lg font-bold text-white capitalize">
                {backendStatus === 'online' ? 'Healthy / Online' : 'Service Offline'}
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Endpoint: /health (SELECT 1)
            </p>
          </div>
        </div>

        {/* Inference Status */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Local Ollama
            </span>
            <Cpu className="w-4 h-4 text-violet-400" />
          </div>

          <div>
            <span className="text-lg font-bold text-white">llama3.2:3b</span>
            <p className="text-xs text-emerald-400 flex items-center gap-1 mt-1 font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Zero-cost Local Execution</span>
            </p>
          </div>
        </div>
      </div>

      {/* Configured Scheduled Jobs */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <span>Configured APScheduler Jobs ({schedulerStatus?.jobs?.length || 0})</span>
          </h3>

          <span className="text-xs text-slate-400">
            Automated background cycles
          </span>
        </div>

        {(!schedulerStatus?.jobs || schedulerStatus.jobs.length === 0) ? (
          <p className="text-xs text-slate-500 italic py-4 text-center">
            No scheduled jobs reported by backend daemon.
          </p>
        ) : (
          <div className="space-y-3">
            {schedulerStatus.jobs.map((job) => {
              const nextRun = job.next_run_time
                ? new Date(job.next_run_time).toLocaleString()
                : 'Not scheduled / Pending cycle';

              return (
                <div
                  key={job.id}
                  className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-white">{job.name}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        {job.id}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                      <span>Trigger: <strong className="text-indigo-400">{job.trigger}</strong></span>
                      <span>•</span>
                      <span>Next Run: <strong className="text-cyan-300">{nextRun}</strong></span>
                    </div>
                  </div>

                  {/* Manual Run Action */}
                  <div className="flex items-center gap-2">
                    {job.id === 'weekly_brief_job' && (
                      <button
                        onClick={handleRunWeeklyBriefs}
                        disabled={isRunningJob !== null}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow disabled:opacity-50"
                      >
                        <Play className={`w-3 h-3 ${isRunningJob === 'briefs' ? 'animate-spin' : ''}`} />
                        <span>{isRunningJob === 'briefs' ? 'Generating...' : 'Run Briefs Now'}</span>
                      </button>
                    )}

                    {job.id === 'monthly_source_health_audit_job' && (
                      <button
                        onClick={handleRunSourceAudit}
                        disabled={isRunningJob !== null}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow disabled:opacity-50"
                      >
                        <Play className={`w-3 h-3 ${isRunningJob === 'audit' ? 'animate-spin' : ''}`} />
                        <span>{isRunningJob === 'audit' ? 'Auditing...' : 'Run Audit Now'}</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
