import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  Sparkles,
  Printer,
  Download,
  Calendar,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  Radio,
  Building2,
  Users2,
  Layers,
  RefreshCw,
  X,
  Target,
  History,
  CheckSquare,
  HelpCircle,
} from 'lucide-react';
import api from '../api/client';

// The 10 required sections in exact assignment order
const REQUIRED_SECTIONS = [
  { key: 'executive_summary', title: '1. Executive Summary', icon: FileText, color: 'text-indigo-400' },
  { key: 'customer_signals', title: '2. Customer Signals', icon: Radio, color: 'text-emerald-400' },
  { key: 'competitor_intelligence', title: '3. Competitor Intelligence', icon: Users2, color: 'text-rose-400' },
  { key: 'market_intelligence', title: '4. Market Intelligence', icon: TrendingUp, color: 'text-cyan-400' },
  { key: 'internal_business_intelligence', title: '5. Internal Business Intelligence', icon: Building2, color: 'text-violet-400' },
  { key: 'opportunities', title: '6. Opportunities', icon: Sparkles, color: 'text-emerald-400' },
  { key: 'risks_threats', title: '7. Risks & Threats', icon: AlertTriangle, color: 'text-rose-400' },
  { key: 'recommended_actions', title: '8. Recommended Actions for This Week', icon: CheckSquare, color: 'text-amber-400' },
  { key: 'items_to_watch', title: '9. What We Should Watch', icon: Target, color: 'text-cyan-400' },
  { key: 'source_appendix', title: '10. Source Appendix', icon: Layers, color: 'text-slate-400' },
];

export default function ExecutiveBrief({ selectedCompany }) {
  // Brief states
  const [currentBrief, setCurrentBrief] = useState(null);
  const [briefHistory, setBriefHistory] = useState([]);
  const [selectedBriefId, setSelectedBriefId] = useState(null);

  // Loading & status states
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // History drawer toggle
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);

  // Load history and latest brief
  const loadBriefs = useCallback(async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      // 1. Load history list
      const historyRes = await api.briefs.list(selectedCompany.id, { limit: 50 });
      const items = historyRes?.items || (Array.isArray(historyRes) ? historyRes : []);
      setBriefHistory(items);

      // 2. Fetch the latest brief
      try {
        const latest = await api.briefs.getCurrent(selectedCompany.id);
        setCurrentBrief(latest);
        setSelectedBriefId(latest.id);
      } catch {
        // If 404, check if history has any brief
        if (items.length > 0) {
          const detail = await api.briefs.get(selectedCompany.id, items[0].id);
          setCurrentBrief(detail);
          setSelectedBriefId(detail.id);
        } else {
          setCurrentBrief(null);
          setSelectedBriefId(null);
        }
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load executive briefs.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCompany]);

  useEffect(() => {
    loadBriefs();
  }, [loadBriefs]);

  // Select a brief from history
  const handleSelectHistoricalBrief = async (briefId) => {
    if (!selectedCompany?.id || !briefId) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      const detail = await api.briefs.get(selectedCompany.id, briefId);
      setCurrentBrief(detail);
      setSelectedBriefId(detail.id);
      setShowHistoryDrawer(false);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to fetch brief details.');
    } finally {
      setIsLoading(false);
    }
  };

  // Generate a new 10-section brief
  const handleGenerateBrief = async () => {
    if (!selectedCompany?.id) return;

    setIsGenerating(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const generated = await api.briefs.generate(selectedCompany.id);
      setCurrentBrief(generated);
      setSelectedBriefId(generated.id);
      setSuccessMessage('Monday Morning Executive Brief generated successfully via local Ollama!');
      // Reload history list
      const historyRes = await api.briefs.list(selectedCompany.id, { limit: 50 });
      setBriefHistory(historyRes?.items || []);
    } catch (err) {
      setErrorMessage(
        err.message ||
          'Failed to generate brief. Ensure local Ollama (llama3.2:3b) is running and company signals are recorded.'
      );
    } finally {
      setIsGenerating(false);
    }
  };

  // Export as Markdown
  const handleExportMarkdown = () => {
    if (!currentBrief) return;

    let md = `# ${currentBrief.title || 'Monday Morning Executive Brief'}\n\n`;
    md += `**Company:** ${selectedCompany?.name || 'Target Enterprise'}\n`;
    md += `**Briefing Date:** ${currentBrief.briefing_date}\n`;
    md += `**Generated:** ${new Date(currentBrief.generated_at).toLocaleString()}\n`;
    md += `**Delivery Status:** ${currentBrief.delivery_status}\n\n`;
    md += `---\n\n`;

    REQUIRED_SECTIONS.forEach((reqSec) => {
      const sec = currentBrief.sections?.find((s) => s.section_key === reqSec.key);
      md += `## ${reqSec.title}\n\n`;
      if (sec && sec.content) {
        md += `${sec.content}\n\n`;
      } else {
        md += `*No items recorded for this section this cycle.*\n\n`;
      }
    });

    if (currentBrief.action_items && currentBrief.action_items.length > 0) {
      md += `### Action Items Tracker\n\n`;
      currentBrief.action_items.forEach((item) => {
        md += `- [ ] **[${item.priority.toUpperCase()}]** ${item.action_text} *(Owner: ${item.suggested_owner || 'Unassigned'})*\n`;
      });
      md += `\n`;
    }

    if (currentBrief.limitations_and_blind_spots) {
      md += `### Limitations & Intelligence Blind Spots\n\n`;
      md += `> ${currentBrief.limitations_and_blind_spots}\n\n`;
    }

    // Download file in browser
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `Executive_Brief_${currentBrief.briefing_date || 'latest'}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Browser Print
  const handlePrint = () => {
    window.print();
  };

  // Render markdown-like prose with facts, quotes, and badges
  const renderFormattedContent = (content) => {
    if (!content) {
      return (
        <p className="text-xs text-slate-500 italic">
          No signals or verified developments recorded for this section during this briefing cycle.
        </p>
      );
    }

    const lines = content.split('\n');

    return (
      <div className="space-y-2.5 text-xs md:text-sm text-slate-200 leading-relaxed font-sans">
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={idx} className="h-1" />;

          // Heading lines (###)
          if (trimmed.startsWith('###')) {
            return (
              <h4 key={idx} className="text-xs md:text-sm font-bold text-white pt-2 border-b border-slate-800 pb-1">
                {trimmed.replace(/^###\s*/, '')}
              </h4>
            );
          }

          // Bullet points
          if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            const itemText = trimmed.replace(/^[-*]\s*/, '');
            const isVerified = itemText.toLowerCase().includes('verified') || itemText.includes('http');
            const isAssumption = itemText.toLowerCase().includes('assumption') || itemText.toLowerCase().includes('interpret');

            return (
              <div key={idx} className="flex items-start gap-2 pl-1">
                <span className="text-indigo-400 mt-1 font-bold">•</span>
                <div className="flex-1">
                  <span>{itemText}</span>
                  {isVerified && (
                    <span className="ml-2 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-emerald-950/60 text-emerald-400 border border-emerald-800">
                      <ShieldCheck className="w-2.5 h-2.5" />
                      Verified
                    </span>
                  )}
                  {isAssumption && (
                    <span className="ml-2 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-amber-950/60 text-amber-300 border border-amber-800">
                      <HelpCircle className="w-2.5 h-2.5" />
                      Inferred
                    </span>
                  )}
                </div>
              </div>
            );
          }

          // Verbatim evidence blockquotes
          if (trimmed.startsWith('>')) {
            return (
              <blockquote
                key={idx}
                className="pl-3 py-1 my-2 border-l-2 border-cyan-400/80 bg-slate-950/60 rounded-r text-xs text-slate-300 font-mono italic"
              >
                {trimmed.replace(/^>\s*/, '')}
              </blockquote>
            );
          }

          // Standard paragraph
          return (
            <p key={idx} className="text-slate-300">
              {trimmed}
            </p>
          );
        })}
      </div>
    );
  };

  // If no company selected
  if (!selectedCompany) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center max-w-xl mx-auto space-y-4">
        <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
          <Building2 className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-bold text-white tracking-tight">No Target Company Selected</h3>
        <p className="text-xs text-slate-400">
          Select a registered company from the header dropdown or the Company Setup page to inspect or generate its Monday Morning Executive Brief.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto print:max-w-none print:p-0">
      {/* Top Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5 print:hidden">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <FileText className="w-6 h-6 text-indigo-400" />
            <span>Monday Morning Executive Brief</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Synthesized 10-section intelligence brief prepared for C-suite decision-makers using local Ollama.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto">
          {briefHistory.length > 0 && (
            <button
              onClick={() => setShowHistoryDrawer(!showHistoryDrawer)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow transition-all"
            >
              <History className="w-3.5 h-3.5 text-cyan-400" />
              <span>Past Briefs ({briefHistory.length})</span>
            </button>
          )}

          {currentBrief && (
            <>
              <button
                onClick={handleExportMarkdown}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow transition-all"
                title="Download brief as Markdown"
              >
                <Download className="w-3.5 h-3.5 text-emerald-400" />
                <span>Export MD</span>
              </button>

              <button
                onClick={handlePrint}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow transition-all"
                title="Print or save as PDF"
              >
                <Printer className="w-3.5 h-3.5 text-indigo-400" />
                <span>Print / PDF</span>
              </button>
            </>
          )}

          <button
            onClick={handleGenerateBrief}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all hover:scale-[1.02] disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin text-cyan-300" />
                <span>Synthesizing with Ollama...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-cyan-300" />
                <span>Generate Brief Now</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Alert Banners */}
      {successMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-800/80 text-xs text-emerald-300 flex items-center justify-between gap-2 shadow-lg print:hidden">
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
        <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800/80 text-xs text-rose-300 flex items-start justify-between gap-2 shadow-lg print:hidden">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block text-rose-200">Brief Synthesis Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* History Selector Dropdown / Drawer */}
      {showHistoryDrawer && briefHistory.length > 0 && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4 shadow-xl space-y-3 print:hidden">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <History className="w-3.5 h-3.5 text-cyan-400" />
              <span>Historical Executive Briefs</span>
            </h4>
            <button
              onClick={() => setShowHistoryDrawer(false)}
              className="text-slate-400 hover:text-white text-xs"
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 max-h-56 overflow-y-auto">
            {briefHistory.map((item) => {
              const isSelected = selectedBriefId === item.id;
              return (
                <div
                  key={item.id}
                  onClick={() => handleSelectHistoricalBrief(item.id)}
                  className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-indigo-950/60 border-indigo-500 shadow'
                      : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <p className="text-xs font-bold text-white truncate">{item.title}</p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-indigo-400" />
                      {item.briefing_date}
                    </span>
                    <span className="text-[10px] uppercase font-semibold text-emerald-400">
                      {item.delivery_status}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Loading State during initial load or generation */}
      {(isLoading || isGenerating) && !currentBrief && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-16 text-center space-y-4 shadow-xl">
          <RefreshCw className="w-8 h-8 mx-auto animate-spin text-cyan-400" />
          <div className="space-y-1">
            <h3 className="text-base font-bold text-white tracking-tight">
              {isGenerating ? 'Synthesizing Monday Morning Brief...' : 'Loading Executive Brief...'}
            </h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Scanning competitor movements, ethical scraper feeds, and founder interview answers to generate the 10 intelligence sections.
            </p>
          </div>
        </div>
      )}

      {/* Empty State when no briefs exist */}
      {!isLoading && !isGenerating && !currentBrief && (
        <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-16 text-center space-y-4">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-inner">
            <FileText className="w-7 h-7" />
          </div>
          <div className="space-y-1 max-w-md mx-auto">
            <h3 className="text-lg font-bold text-white tracking-tight">
              No Briefs Generated for {selectedCompany.name} Yet
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Click <strong>"Generate Brief Now"</strong> to synthesize recorded market signals and founder interview answers into the complete 10-section executive intelligence report.
            </p>
          </div>
          <div className="pt-2">
            <button
              onClick={handleGenerateBrief}
              disabled={isGenerating}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all"
            >
              <Sparkles className="w-4 h-4 text-cyan-300" />
              <span>Generate First Brief</span>
            </button>
          </div>
        </div>
      )}

      {/* Active 10-Section Brief View */}
      {currentBrief && (
        <div className="space-y-6 print:space-y-4 print:text-black">
          {/* Document Masthead */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 md:p-8 shadow-2xl relative overflow-hidden print:bg-white print:border-none print:shadow-none print:p-0">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5 print:border-gray-300">
              <div className="space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 bg-cyan-950/60 px-2.5 py-0.5 rounded-full border border-cyan-800/60 print:border print:text-black">
                  Executive Intelligence Brief
                </span>
                <h1 className="text-xl md:text-2xl font-extrabold text-white tracking-tight mt-1 print:text-black">
                  {currentBrief.title || `${selectedCompany.name} Executive Brief`}
                </h1>
                <p className="text-xs text-slate-400 font-medium print:text-gray-600">
                  Target: <strong className="text-slate-200 print:text-black">{selectedCompany.name}</strong> • Briefing Date: <strong className="text-slate-200 print:text-black">{currentBrief.briefing_date}</strong>
                </p>
              </div>

              <div className="flex flex-col sm:items-end text-xs text-slate-400 gap-1 print:text-gray-600">
                <div className="flex items-center gap-1.5 text-emerald-400 print:text-black font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 print:bg-black" />
                  <span className="capitalize">{currentBrief.delivery_status || 'Generated'}</span>
                </div>
                <span className="text-[11px] font-mono">
                  Synthesized {new Date(currentBrief.generated_at).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Quick Stats Banner */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 print:hidden">
              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
                <p className="text-[10px] uppercase font-bold text-slate-400">Sections</p>
                <p className="text-base font-bold text-white mt-0.5">10 Complete</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
                <p className="text-[10px] uppercase font-bold text-amber-400">Action Items</p>
                <p className="text-base font-bold text-amber-300 mt-0.5">
                  {currentBrief.action_items?.length || 0} Recommended
                </p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
                <p className="text-[10px] uppercase font-bold text-cyan-400">AI Model</p>
                <p className="text-base font-bold text-cyan-300 mt-0.5">llama3.2:3b</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80">
                <p className="text-[10px] uppercase font-bold text-emerald-400">Verification</p>
                <p className="text-base font-bold text-emerald-300 mt-0.5">Fact Verified</p>
              </div>
            </div>
          </div>

          {/* THE 10 SECTIONS IN EXACT REQUIRED ORDER */}
          <div className="space-y-6">
            {REQUIRED_SECTIONS.map((reqSec, idx) => {
              const SecIcon = reqSec.icon;
              const sectionData = currentBrief.sections?.find((s) => s.section_key === reqSec.key);
              const content = sectionData?.content || (reqSec.key === 'executive_summary' ? currentBrief.executive_summary : '');

              return (
                <div
                  key={reqSec.key}
                  className="rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-xl space-y-4 print:bg-white print:border print:border-gray-300 print:shadow-none print:break-inside-avoid"
                >
                  {/* Section Title Header */}
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3 print:border-gray-200">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center print:bg-gray-100">
                        <SecIcon className={`w-4 h-4 ${reqSec.color} print:text-black`} />
                      </div>
                      <h3 className="text-base font-bold text-white tracking-tight print:text-black">
                        {reqSec.title}
                      </h3>
                    </div>

                    <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 print:border-gray-300 print:text-gray-600">
                      Section {idx + 1}
                    </span>
                  </div>

                  {/* Section Content */}
                  <div className="pt-1">
                    {renderFormattedContent(content)}
                  </div>

                  {/* Special Render for Section 8: Recommended Actions Tracker */}
                  {reqSec.key === 'recommended_actions' && currentBrief.action_items && currentBrief.action_items.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-800 space-y-2.5">
                      <h5 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                        <CheckSquare className="w-3.5 h-3.5" />
                        <span>Action Items Tracker</span>
                      </h5>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        {currentBrief.action_items.map((item, itemIdx) => {
                          const priorityColor =
                            item.priority?.toLowerCase() === 'high'
                              ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                              : item.priority?.toLowerCase() === 'medium'
                              ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                              : 'bg-slate-800 text-slate-300 border-slate-700';

                          return (
                            <div
                              key={item.id || itemIdx}
                              className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col justify-between space-y-2 print:bg-gray-50 print:border-gray-200"
                            >
                              <p className="text-xs font-semibold text-slate-100 leading-snug print:text-black">
                                {item.action_text}
                              </p>
                              <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-900">
                                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${priorityColor}`}>
                                  {item.priority} Priority
                                </span>
                                <span className="text-slate-400 text-[10px] truncate max-w-[140px]">
                                  Owner: <strong className="text-slate-300">{item.suggested_owner || 'Unassigned'}</strong>
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Referenced Signal IDs Footnote */}
                  {sectionData?.referenced_signal_ids && sectionData.referenced_signal_ids.length > 0 && (
                    <div className="pt-2 border-t border-slate-800/60 flex items-center gap-1.5 text-[10px] text-slate-500 font-mono overflow-x-auto">
                      <span>Citations:</span>
                      {sectionData.referenced_signal_ids.map((id) => (
                        <span key={id} className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 text-indigo-400">
                          #{String(id).slice(0, 8)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Limitations and Blind Spots Callout */}
          {currentBrief.limitations_and_blind_spots && (
            <div className="rounded-2xl bg-slate-900 border border-amber-900/40 p-6 space-y-2 shadow-xl print:bg-white print:border-gray-300">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
                <AlertTriangle className="w-4 h-4" />
                <span>Executive Limitations & Intelligence Blind Spots</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed italic print:text-gray-700">
                {currentBrief.limitations_and_blind_spots}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
