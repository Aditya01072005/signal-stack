import React, { useState } from 'react';
import {
  Building2,
  Globe,
  PlusCircle,
  Search,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Layers,
  ShieldCheck,
  HelpCircle,
  ChevronRight,
  RefreshCw,
  Tag,
  Briefcase,
  Target,
  FileCheck2,
  FileQuestion,
} from 'lucide-react';
import api from '../api/client';

export default function CompanySetup({
  companies = [],
  selectedCompany,
  onSelectCompany,
  onCompanyCreated,
  isLoadingCompanies,
  onRefreshCompanies,
}) {
  // Registration Form State
  const [formData, setFormData] = useState({
    name: '',
    website_url: '',
    industry: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registerError, setRegisterError] = useState(null);
  const [registerSuccess, setRegisterSuccess] = useState(null);

  // Search / Filter Companies State
  const [searchTerm, setSearchTerm] = useState('');

  // Research State (keyed by company id for caching in component session)
  const [researchProfiles, setResearchProfiles] = useState({});
  const [isResearching, setIsResearching] = useState(false);
  const [researchError, setResearchError] = useState(null);
  const [activeProfileTab, setActiveProfileTab] = useState('facts_assumptions'); // 'facts_assumptions' | 'products' | 'positioning'

  // Handle Form Submit
  const handleRegister = async (e) => {
    e.preventDefault();
    setRegisterError(null);
    setRegisterSuccess(null);

    const name = formData.name.trim();
    let url = formData.website_url.trim();
    const industry = formData.industry.trim() || undefined;

    if (!name) {
      setRegisterError('Company name is required.');
      return;
    }
    if (!url) {
      setRegisterError('Website URL is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      const newCompany = await api.companies.create({
        name,
        website_url: url,
        industry,
      });

      setRegisterSuccess(`Company "${newCompany.name}" registered successfully.`);
      setFormData({ name: '', website_url: '', industry: '' });

      if (onCompanyCreated) {
        await onCompanyCreated(newCompany);
      }
    } catch (err) {
      setRegisterError(err.message || 'Failed to register company.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Trigger Research
  const handleTriggerResearch = async () => {
    if (!selectedCompany?.id) return;

    setIsResearching(true);
    setResearchError(null);

    try {
      const result = await api.research.trigger(selectedCompany.id);
      setResearchProfiles((prev) => ({
        ...prev,
        [selectedCompany.id]: result,
      }));
    } catch (err) {
      setResearchError(err.message || 'Failed to run company research.');
    } finally {
      setIsResearching(false);
    }
  };

  // Filtered companies list
  const filteredCompanies = companies.filter((c) => {
    const q = searchTerm.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.industry && c.industry.toLowerCase().includes(q)) ||
      c.website_url.toLowerCase().includes(q)
    );
  });

  const activeProfile = selectedCompany?.id ? researchProfiles[selectedCompany.id] : null;

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header Description */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Building2 className="w-6 h-6 text-indigo-400" />
            <span>Company Setup & Autonomous Research</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Register target enterprises, scrape public sites with ethical rate-limiting, and synthesize Fact vs Assumption baselines.
          </p>
        </div>

        {selectedCompany && (
          <div className="flex items-center gap-2 self-start md:self-auto bg-slate-900 border border-slate-800 px-3.5 py-1.5 rounded-xl">
            <span className="text-xs text-slate-400">Target Selected:</span>
            <span className="text-xs font-semibold text-cyan-400 truncate max-w-[180px]">
              {selectedCompany.name}
            </span>
          </div>
        )}
      </div>

      {/* Main Grid: Left Column (Form & List) | Right Column (Research Workspace) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* LEFT COLUMN: 5 cols on lg */}
        <div className="lg:col-span-5 space-y-6">
          {/* Registration Form Card */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 shadow-xl">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 mb-4">
              <PlusCircle className="w-4 h-4 text-indigo-400" />
              <span>Register New Target</span>
            </h3>

            {registerSuccess && (
              <div className="mb-4 p-3 rounded-lg bg-emerald-950/70 border border-emerald-800/80 text-xs text-emerald-300 flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <span>{registerSuccess}</span>
              </div>
            )}

            {registerError && (
              <div className="mb-4 p-3 rounded-lg bg-rose-950/70 border border-rose-800/80 text-xs text-rose-300 flex items-start gap-2">
                <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                <span>{registerError}</span>
              </div>
            )}

            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Company Name <span className="text-rose-400">*</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g. Acme Corp"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                  <Building2 className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Public Website URL <span className="text-rose-400">*</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={formData.website_url}
                    onChange={(e) => setFormData({ ...formData, website_url: e.target.value })}
                    placeholder="e.g. https://acme.com or acme.com"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                  <Globe className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Scheme is automatically normalized (defaults to https://).
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Industry / Sector <span className="text-slate-500">(Optional)</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={formData.industry}
                    onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                    placeholder="e.g. Enterprise SaaS / Cybersecurity"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                  <Briefcase className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Registering Target...</span>
                  </>
                ) : (
                  <>
                    <PlusCircle className="w-4 h-4" />
                    <span>Register Company</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Registered Companies List Card */}
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Registered Targets
                </h3>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-semibold border border-slate-700">
                  {companies.length}
                </span>
              </div>

              <button
                onClick={onRefreshCompanies}
                disabled={isLoadingCompanies}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                title="Refresh list"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${isLoadingCompanies ? 'animate-spin text-indigo-400' : ''}`}
                />
              </button>
            </div>

            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Filter by name, website, industry..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            </div>

            {/* List */}
            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
              {isLoadingCompanies && companies.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  <RefreshCw className="w-5 h-5 mx-auto animate-spin text-indigo-400 mb-2" />
                  Loading companies...
                </div>
              ) : filteredCompanies.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-xl p-4">
                  {searchTerm ? 'No companies match search filter.' : 'No companies registered yet. Add one above.'}
                </div>
              ) : (
                filteredCompanies.map((c) => {
                  const isSelected = selectedCompany?.id === c.id;
                  const hasProfile = Boolean(researchProfiles[c.id]);

                  return (
                    <div
                      key={c.id}
                      onClick={() => onSelectCompany(c)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer text-left group relative ${
                        isSelected
                          ? 'bg-indigo-950/40 border-indigo-500 shadow-md shadow-indigo-500/10'
                          : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-sm text-white group-hover:text-indigo-300 transition-colors truncate">
                              {c.name}
                            </span>
                            {hasProfile && (
                              <span
                                className="w-2 h-2 rounded-full bg-emerald-400"
                                title="Intelligence profile generated"
                              />
                            )}
                          </div>

                          <div className="flex items-center gap-1 text-[11px] text-slate-400 mt-1 truncate">
                            <Globe className="w-3 h-3 text-slate-500 flex-shrink-0" />
                            <a
                              href={c.website_url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="hover:text-cyan-400 hover:underline truncate"
                            >
                              {c.website_url}
                            </a>
                            <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                          </div>

                          {c.industry && (
                            <div className="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                              <Tag className="w-2.5 h-2.5 text-indigo-400" />
                              <span>{c.industry}</span>
                            </div>
                          )}
                        </div>

                        <ChevronRight
                          className={`w-4 h-4 flex-shrink-0 mt-1 transition-transform ${
                            isSelected ? 'text-indigo-400 translate-x-0.5' : 'text-slate-600 group-hover:text-slate-400'
                          }`}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: 7 cols on lg (Research & Profile Synthesis) */}
        <div className="lg:col-span-7 space-y-6">
          {selectedCompany ? (
            <div className="space-y-6">
              {/* Trigger Research Header Card */}
              <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-xl relative overflow-hidden">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400 bg-indigo-500/10 px-2.5 py-0.5 rounded-full border border-indigo-500/20">
                      Target Intelligence Workspace
                    </span>
                    <h3 className="text-xl font-bold text-white mt-1.5 tracking-tight">
                      {selectedCompany.name}
                    </h3>
                    <p className="text-xs text-slate-400 font-mono mt-0.5 truncate">
                      {selectedCompany.website_url}
                    </p>
                  </div>

                  <button
                    onClick={handleTriggerResearch}
                    disabled={isResearching}
                    className="self-start sm:self-auto inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-sm font-semibold shadow-lg shadow-indigo-600/30 transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none flex-shrink-0"
                  >
                    {isResearching ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin text-cyan-300" />
                        <span>Extracting with Ollama...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4 text-cyan-300" />
                        <span>{activeProfile ? 'Re-run Research' : 'Run AI Company Research'}</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Research Error Alert */}
                {researchError && (
                  <div className="mt-4 p-4 rounded-xl bg-rose-950/70 border border-rose-800 text-xs text-rose-300 flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block text-rose-200">Research Execution Failed</span>
                      <p className="mt-0.5 leading-relaxed">{researchError}</p>
                    </div>
                  </div>
                )}

                {/* Research in Progress Indicator */}
                {isResearching && (
                  <div className="mt-5 p-4 rounded-xl bg-indigo-950/40 border border-indigo-800/60 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-indigo-300 font-medium flex items-center gap-2">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                        Crawling website & extracting insights with llama3.2:3b...
                      </span>
                      <span className="text-cyan-400 font-mono text-[11px]">EthicalScraper Active</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                      <div className="bg-gradient-to-r from-indigo-500 via-cyan-400 to-indigo-500 h-1.5 w-full animate-pulse" />
                    </div>
                  </div>
                )}
              </div>

              {/* Research Results / Profile Section */}
              {activeProfile ? (
                <div className="space-y-6">
                  {/* Status Banner & Business Summary */}
                  <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-4 shadow-xl">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                        Executive Business Summary
                      </span>
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                          activeProfile.scrape_status === 'success'
                            ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                            : 'bg-amber-950/60 text-amber-400 border-amber-800'
                        }`}
                      >
                        Status: {activeProfile.scrape_status}
                      </span>
                    </div>

                    <p className="text-sm md:text-base text-slate-200 leading-relaxed bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 font-normal italic">
                      "{activeProfile.business_summary || 'No summary text available.'}"
                    </p>

                    {/* Quick Metric Pills */}
                    <div className="flex flex-wrap gap-2.5 pt-2">
                      <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-xs text-emerald-300">
                        <FileCheck2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span>{activeProfile.verified_facts?.length || 0} Verified Facts</span>
                      </div>

                      <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-violet-950/40 border border-violet-800/60 text-xs text-violet-300">
                        <FileQuestion className="w-3.5 h-3.5 text-violet-400" />
                        <span>{activeProfile.assumptions?.length || 0} Unverified Assumptions</span>
                      </div>

                      {activeProfile.facts_excluded > 0 && (
                        <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-950/40 border border-amber-800/60 text-xs text-amber-300">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                          <span>{activeProfile.facts_excluded} Facts Excluded (Unverified)</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Profile Navigation Tabs */}
                  <div className="flex border-b border-slate-800 gap-2">
                    <button
                      onClick={() => setActiveProfileTab('facts_assumptions')}
                      className={`pb-3 px-3 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
                        activeProfileTab === 'facts_assumptions'
                          ? 'border-indigo-500 text-white'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <ShieldCheck className="w-4 h-4 text-indigo-400" />
                      <span>Fact vs Assumption Breakdown</span>
                    </button>

                    <button
                      onClick={() => setActiveProfileTab('products')}
                      className={`pb-3 px-3 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
                        activeProfileTab === 'products'
                          ? 'border-indigo-500 text-white'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Layers className="w-4 h-4 text-cyan-400" />
                      <span>Products & Segments</span>
                    </button>

                    <button
                      onClick={() => setActiveProfileTab('positioning')}
                      className={`pb-3 px-3 text-xs font-semibold tracking-wide border-b-2 transition-all flex items-center gap-1.5 ${
                        activeProfileTab === 'positioning'
                          ? 'border-indigo-500 text-white'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Target className="w-4 h-4 text-emerald-400" />
                      <span>Market Positioning</span>
                    </button>
                  </div>

                  {/* TAB 1: Fact vs Assumption Breakdown */}
                  {activeProfileTab === 'facts_assumptions' && (
                    <div className="space-y-6">
                      {/* Verified Facts Sub-section */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
                            <ShieldCheck className="w-4 h-4" />
                            <span>Verified Facts (Directly on Public Website)</span>
                          </h4>
                          <span className="text-[11px] text-slate-400">
                            Backed by verbatim evidence
                          </span>
                        </div>

                        {!activeProfile.verified_facts || activeProfile.verified_facts.length === 0 ? (
                          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-500">
                            No verified facts matched verbatim evidence.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {activeProfile.verified_facts.map((item, idx) => (
                              <div
                                key={idx}
                                className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-emerald-800/50 transition-colors space-y-2"
                              >
                                <div className="flex items-start gap-2">
                                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                                  <p className="text-sm font-medium text-slate-100 leading-snug">
                                    {item.fact}
                                  </p>
                                </div>

                                {item.evidence_text && (
                                  <div className="pl-6 border-l-2 border-emerald-500/30 my-1 py-0.5">
                                    <p className="text-xs text-slate-400 font-mono italic">
                                      "{item.evidence_text}"
                                    </p>
                                  </div>
                                )}

                                {item.source_url && (
                                  <div className="pl-6 flex items-center gap-1 text-[11px] text-slate-500">
                                    <span>Source:</span>
                                    <a
                                      href={item.source_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-indigo-400 hover:underline truncate max-w-sm"
                                    >
                                      {item.source_url}
                                    </a>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Assumptions Sub-section */}
                      <div className="space-y-3 pt-2">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-violet-400 flex items-center gap-2">
                            <HelpCircle className="w-4 h-4" />
                            <span>Unverified Inferences & Assumptions</span>
                          </h4>
                          <span className="text-[11px] text-slate-400">
                            LLM extrapolations requiring founder validation
                          </span>
                        </div>

                        {!activeProfile.assumptions || activeProfile.assumptions.length === 0 ? (
                          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-500">
                            No assumptions were proposed.
                          </div>
                        ) : (
                          <div className="space-y-2.5">
                            {activeProfile.assumptions.map((item, idx) => (
                              <div
                                key={idx}
                                className="p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-violet-800/50 transition-colors flex items-start justify-between gap-3"
                              >
                                <div className="space-y-1">
                                  <p className="text-sm text-slate-200 leading-snug">
                                    {item.assumption}
                                  </p>
                                  {item.rationale && (
                                    <p className="text-xs text-slate-400">
                                      Rationale: {item.rationale}
                                    </p>
                                  )}
                                </div>

                                <span
                                  className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border flex-shrink-0 ${
                                    item.confidence === 'high'
                                      ? 'bg-violet-950 text-violet-300 border-violet-800'
                                      : item.confidence === 'low'
                                      ? 'bg-slate-800 text-slate-400 border-slate-700'
                                      : 'bg-indigo-950 text-indigo-300 border-indigo-800'
                                  }`}
                                >
                                  {item.confidence || 'medium'} conf
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* TAB 2: Products & Customer Segments */}
                  {activeProfileTab === 'products' && (
                    <div className="space-y-6">
                      {/* Products & Services */}
                      <div className="space-y-3">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                          Identified Products & Services
                        </h4>
                        {!activeProfile.products_services || activeProfile.products_services.length === 0 ? (
                          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-500">
                            No products or services identified.
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {activeProfile.products_services.map((p, idx) => (
                              <div
                                key={idx}
                                className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-1"
                              >
                                <p className="text-sm font-semibold text-white">
                                  {p.name || `Offering #${idx + 1}`}
                                </p>
                                <p className="text-xs text-slate-400 leading-relaxed">
                                  {p.description || 'No description extracted.'}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Customer Segments */}
                      <div className="space-y-3 pt-2">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                          Target Customer Segments
                        </h4>
                        {!activeProfile.customer_segments || activeProfile.customer_segments.length === 0 ? (
                          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-500">
                            No customer segments identified.
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {activeProfile.customer_segments.map((seg, idx) => (
                              <div
                                key={idx}
                                className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-1"
                              >
                                <p className="text-sm font-semibold text-cyan-300">
                                  {seg.segment || `Segment #${idx + 1}`}
                                </p>
                                <p className="text-xs text-slate-400 leading-relaxed">
                                  {seg.description || 'Target profile rationale.'}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* TAB 3: Market Positioning */}
                  {activeProfileTab === 'positioning' && (
                    <div className="space-y-6">
                      <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
                        <div>
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-1">
                            Core Value Proposition
                          </h4>
                          <p className="text-sm text-slate-200 leading-relaxed bg-slate-950 p-3.5 rounded-xl border border-slate-800">
                            {activeProfile.positioning?.value_proposition ||
                              'No specific value proposition extracted.'}
                          </p>
                        </div>

                        {activeProfile.positioning?.differentiators &&
                          activeProfile.positioning.differentiators.length > 0 && (
                            <div>
                              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">
                                Strategic Differentiators
                              </h4>
                              <div className="flex flex-wrap gap-2">
                                {activeProfile.positioning.differentiators.map((diff, idx) => (
                                  <span
                                    key={idx}
                                    className="px-3 py-1.5 rounded-lg bg-indigo-950/60 border border-indigo-800/80 text-xs text-indigo-300 font-medium"
                                  >
                                    {diff}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                /* Empty state when no research yet for selected company */
                <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-center space-y-3">
                  <div className="w-12 h-12 mx-auto rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <h4 className="text-base font-bold text-white tracking-tight">
                    No Intelligence Profile Generated Yet
                  </h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Click <strong>"Run AI Company Research"</strong> above to scrape{' '}
                    <span className="text-cyan-400 font-mono">{selectedCompany.website_url}</span> and
                    have local Ollama (<code className="text-slate-300">llama3.2:3b</code>) synthesize
                    the Fact vs Assumption baseline.
                  </p>
                </div>
              )}
            </div>
          ) : (
            /* Empty state when no company is selected */
            <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center space-y-3">
              <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
                <Building2 className="w-6 h-6" />
              </div>
              <h4 className="text-base font-bold text-white tracking-tight">
                Select or Register a Company
              </h4>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Choose a company from the left column or register a new one to unlock the autonomous research workspace.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
