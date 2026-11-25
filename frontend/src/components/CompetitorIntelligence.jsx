import React, { useState, useEffect, useCallback } from 'react';
import {
  Users2,
  PlusCircle,
  Sparkles,
  ExternalLink,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  Building2,
  Edit3,
  Power,
  ShieldCheck,
  ShieldAlert,
  Target,
  GitFork,
  Shuffle,
  X,
  Check,
} from 'lucide-react';
import api from '../api/client';

const TIERS = [
  { id: 'direct', label: 'Direct Competitors', desc: 'Same product & target customers', icon: Target, color: 'text-rose-400', badge: 'bg-rose-950/80 text-rose-300 border-rose-800' },
  { id: 'indirect', label: 'Indirect Competitors', desc: 'Different product solving overlapping need', icon: GitFork, color: 'text-amber-400', badge: 'bg-amber-950/80 text-amber-300 border-amber-800' },
  { id: 'substitute', label: 'Substitute Competitors', desc: 'Alternative category or internal DIY workaround', icon: Shuffle, color: 'text-violet-400', badge: 'bg-violet-950/80 text-violet-300 border-violet-800' },
];

export default function CompetitorIntelligence({ selectedCompany }) {
  // Competitor list state
  const [competitors, setCompetitors] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Filters & Search
  const [tierFilter, setTierFilter] = useState('all'); // 'all' | 'direct' | 'indirect' | 'substitute'
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'active' | 'inactive'
  const [searchQuery, setSearchQuery] = useState('');

  // Add / Edit Form State
  const [showForm, setShowForm] = useState(false);
  const [editingCompetitorId, setEditingCompetitorId] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    website_url: '',
    competitor_type: 'direct',
    description: '',
    evidence_url: '',
    notes: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  // AI Discovery Suggestions State
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [showSuggestionsPanel, setShowSuggestionsPanel] = useState(false);
  const [approvingSuggestionIndex, setApprovingSuggestionIndex] = useState(null);

  // Per-competitor action loading
  const [togglingId, setTogglingId] = useState(null);

  // Load competitors for selected company
  const loadCompetitors = useCallback(async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.competitors.list(selectedCompany.id, {
        include_inactive: true,
      });
      const items = Array.isArray(res) ? res : res?.items || [];
      setCompetitors(items);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load competitors.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCompany]);

  useEffect(() => {
    loadCompetitors();
  }, [loadCompetitors]);

  // Open Add Form
  const handleOpenAddForm = () => {
    setEditingCompetitorId(null);
    setFormData({
      name: '',
      website_url: '',
      competitor_type: 'direct',
      description: '',
      evidence_url: '',
      notes: '',
    });
    setFormError(null);
    setShowForm(true);
  };

  // Open Edit Form
  const handleOpenEditForm = (c) => {
    setEditingCompetitorId(c.id);
    setFormData({
      name: c.name,
      website_url: c.website_url || '',
      competitor_type: c.competitor_type || 'direct',
      description: c.description || '',
      evidence_url: c.evidence_url || '',
      notes: c.notes || '',
    });
    setFormError(null);
    setShowForm(true);
  };

  // Handle Form Submit (Create or Update)
  const handleSubmitForm = async (e) => {
    e.preventDefault();
    if (!selectedCompany?.id) return;

    const name = formData.name.trim();
    let url = formData.website_url.trim() || undefined;
    if (url && !url.toLowerCase().startsWith('http://') && !url.toLowerCase().startsWith('https://')) {
      url = `https://${url}`;
    }

    let evidence = formData.evidence_url.trim() || undefined;
    if (evidence && !evidence.toLowerCase().startsWith('http://') && !evidence.toLowerCase().startsWith('https://')) {
      evidence = `https://${evidence}`;
    }

    if (!name) {
      setFormError('Competitor name is required.');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      if (editingCompetitorId) {
        // Update
        const updated = await api.competitors.update(selectedCompany.id, editingCompetitorId, {
          name,
          website_url: url,
          competitor_type: formData.competitor_type,
          description: formData.description.trim() || undefined,
          evidence_url: evidence,
        });
        setCompetitors((prev) =>
          prev.map((item) => (item.id === editingCompetitorId ? updated : item))
        );
        setSuccessMessage(`Competitor "${updated.name}" updated successfully.`);
      } else {
        // Create
        const created = await api.competitors.create(selectedCompany.id, {
          name,
          website_url: url,
          competitor_type: formData.competitor_type,
          description: formData.description.trim() || undefined,
          evidence_url: evidence,
        });
        setCompetitors((prev) => [...prev, created]);
        setSuccessMessage(`Competitor "${created.name}" added to intelligence tracking.`);
      }

      setShowForm(false);
      setEditingCompetitorId(null);
    } catch (err) {
      setFormError(err.message || 'Failed to save competitor.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Soft-deactivate or reactivate
  const handleToggleActive = async (c) => {
    if (!selectedCompany?.id) return;

    setTogglingId(c.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      if (c.is_active) {
        // Soft deactivate (preserves history)
        const updated = await api.competitors.deactivate(selectedCompany.id, c.id);
        setCompetitors((prev) =>
          prev.map((item) => (item.id === c.id ? updated : item))
        );
        setSuccessMessage(`Competitor "${c.name}" deactivated (historical briefs preserved).`);
      } else {
        // Reactivate
        const updated = await api.competitors.update(selectedCompany.id, c.id, {
          is_active: true,
        });
        setCompetitors((prev) =>
          prev.map((item) => (item.id === c.id ? updated : item))
        );
        setSuccessMessage(`Competitor "${c.name}" reactivated.`);
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update competitor status.');
    } finally {
      setTogglingId(null);
    }
  };

  // Discover Competitor Suggestions with AI
  const handleDiscoverCompetitors = async () => {
    if (!selectedCompany?.id) return;

    setIsDiscovering(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.competitors.discover(selectedCompany.id);
      const suggestions = res?.suggestions || [];
      setAiSuggestions(suggestions);
      setShowSuggestionsPanel(true);
      setSuccessMessage(`Generated ${suggestions.length} AI competitor suggestions using llama3.2:3b.`);
    } catch (err) {
      if (err.status === 422 && String(err.message).toLowerCase().includes('profile')) {
        setErrorMessage('Company research profile not found. Please run "AI Company Research" in Companies & Intel before running competitor discovery.');
      } else {
        setErrorMessage(err.message || 'Failed to run AI competitor discovery.');
      }
    } finally {
      setIsDiscovering(false);
    }
  };

  // Approve an unverified AI suggestion
  const handleApproveSuggestion = async (sug, index) => {
    if (!selectedCompany?.id) return;

    setApprovingSuggestionIndex(index);
    setErrorMessage(null);
    try {
      const created = await api.competitors.create(selectedCompany.id, {
        name: sug.name,
        website_url: sug.website_url || undefined,
        competitor_type: sug.competitor_type,
        description: sug.description,
        evidence_url: sug.evidence_url || undefined,
      });

      setCompetitors((prev) => [...prev, created]);
      // Remove from suggestions list
      setAiSuggestions((prev) => prev.filter((_, idx) => idx !== index));
      setSuccessMessage(`Approved & added "${created.name}" to verified competitors.`);
    } catch (err) {
      setErrorMessage(err.message || `Failed to add competitor "${sug.name}".`);
    } finally {
      setApprovingSuggestionIndex(null);
    }
  };

  // Filter calculations
  const totalCount = competitors.length;
  const directCount = competitors.filter((c) => c.competitor_type === 'direct').length;
  const indirectCount = competitors.filter((c) => c.competitor_type === 'indirect').length;
  const substituteCount = competitors.filter((c) => c.competitor_type === 'substitute').length;

  const filteredCompetitors = competitors.filter((c) => {
    // Tier filter
    if (tierFilter !== 'all' && c.competitor_type !== tierFilter) return false;

    // Status filter
    if (statusFilter === 'active' && !c.is_active) return false;
    if (statusFilter === 'inactive' && c.is_active) return false;

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = c.name?.toLowerCase().includes(q);
      const matchUrl = c.website_url?.toLowerCase().includes(q);
      const matchDesc = c.description?.toLowerCase().includes(q);
      if (!matchName && !matchUrl && !matchDesc) return false;
    }

    return true;
  });

  // Group filtered competitors by tier
  const groupedCompetitors = {
    direct: filteredCompetitors.filter((c) => c.competitor_type === 'direct'),
    indirect: filteredCompetitors.filter((c) => c.competitor_type === 'indirect'),
    substitute: filteredCompetitors.filter((c) => c.competitor_type === 'substitute'),
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
          Select a registered company from the header dropdown or the Company Setup page to view and map its competitor intelligence.
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
            <Users2 className="w-6 h-6 text-indigo-400" />
            <span>Competitor Intelligence & Tier Mapping</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Map competitors across Direct, Indirect, and Substitute tiers with evidence URLs and AI discovery.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto">
          <button
            onClick={handleDiscoverCompetitors}
            disabled={isDiscovering}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow-md transition-all disabled:opacity-50"
            title="Analyze research profile and suggest competitors with Ollama"
          >
            <Sparkles className={`w-3.5 h-3.5 text-cyan-400 ${isDiscovering ? 'animate-spin' : ''}`} />
            <span>{isDiscovering ? 'Analyzing Profile with AI...' : 'Discover with AI'}</span>
          </button>

          <button
            onClick={handleOpenAddForm}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all hover:scale-[1.02]"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Add Competitor</span>
          </button>

          <button
            onClick={loadCompetitors}
            disabled={isLoading}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Refresh list"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Total Competitors</p>
            <p className="text-xl font-bold text-white mt-0.5">{totalCount}</p>
          </div>
          <Users2 className="w-5 h-5 text-indigo-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-rose-400 font-medium">Direct Tiers</p>
            <p className="text-xl font-bold text-rose-300 mt-0.5">{directCount}</p>
          </div>
          <Target className="w-5 h-5 text-rose-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-amber-400 font-medium">Indirect Tiers</p>
            <p className="text-xl font-bold text-amber-300 mt-0.5">{indirectCount}</p>
          </div>
          <GitFork className="w-5 h-5 text-amber-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-violet-400 font-medium">Substitutes</p>
            <p className="text-xl font-bold text-violet-300 mt-0.5">{substituteCount}</p>
          </div>
          <Shuffle className="w-5 h-5 text-violet-400" />
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
              <span className="font-semibold block text-rose-200">Competitor Intelligence Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* AI SUGGESTIONS DRAWER (UNVERIFIED) */}
      {showSuggestionsPanel && aiSuggestions.length > 0 && (
        <div className="rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-900 border border-indigo-500/40 p-5 shadow-2xl space-y-4">
          <div className="flex items-center justify-between border-b border-indigo-500/20 pb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                AI Suggested Competitors ({aiSuggestions.length})
              </h3>
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800">
                Unverified Inferences
              </span>
            </div>

            <button
              onClick={() => setShowSuggestionsPanel(false)}
              className="text-slate-400 hover:text-white text-xs flex items-center gap-1"
            >
              <span>Dismiss Panel</span>
              <X className="w-4 h-4" />
            </button>
          </div>

          <p className="text-xs text-slate-300">
            The following competitors were inferred by <span className="font-mono text-cyan-300">llama3.2:3b</span> from the company research profile. They are marked <strong>Unverified</strong> until reviewed and saved with source evidence.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {aiSuggestions.map((sug, idx) => {
              const isApproving = approvingSuggestionIndex === idx;

              return (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-slate-950/80 border border-indigo-500/30 hover:border-indigo-400/60 transition-all flex flex-col justify-between space-y-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-bold text-sm text-white truncate">{sug.name}</span>
                      <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        {sug.competitor_type}
                      </span>
                    </div>

                    {sug.website_url && (
                      <p className="text-[11px] text-cyan-400 font-mono truncate">{sug.website_url}</p>
                    )}

                    <p className="text-xs text-slate-300 leading-snug">{sug.description}</p>

                    {sug.ai_rationale && (
                      <div className="p-2 rounded bg-indigo-950/40 border border-indigo-900/60 text-[11px] text-slate-400 mt-2">
                        <strong className="text-indigo-300 block mb-0.5">AI Rationale:</strong>
                        {sug.ai_rationale}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 flex items-center justify-between border-t border-slate-800">
                    <span className="text-[10px] text-amber-400 flex items-center gap-1">
                      <ShieldAlert className="w-3 h-3" /> Unverified
                    </span>

                    <button
                      onClick={() => handleApproveSuggestion(sug, idx)}
                      disabled={isApproving}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow disabled:opacity-50"
                    >
                      {isApproving ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Check className="w-3 h-3" />
                      )}
                      <span>Approve & Save</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Add / Edit Competitor Modal Form */}
      {showForm && (
        <div className="rounded-2xl bg-slate-900 border border-indigo-500/50 p-6 shadow-2xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Users2 className="w-4 h-4 text-indigo-400" />
              <span>{editingCompetitorId ? 'Edit Competitor Profile' : 'Add Competitor Profile'}</span>
            </h3>
            <button
              onClick={() => {
                setShowForm(false);
                setEditingCompetitorId(null);
              }}
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {formError && (
            <div className="p-3 rounded-lg bg-rose-950/70 border border-rose-800 text-xs text-rose-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{formError}</span>
            </div>
          )}

          <form onSubmit={handleSubmitForm} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Competitor Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. RivalSoft Inc."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Website URL <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.website_url}
                  onChange={(e) => setFormData({ ...formData, website_url: e.target.value })}
                  placeholder="e.g. https://rivalsoft.com"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Strategic Tier <span className="text-rose-400">*</span>
                </label>
                <select
                  value={formData.competitor_type}
                  onChange={(e) => setFormData({ ...formData, competitor_type: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  <option value="direct">Direct (Same product & target)</option>
                  <option value="indirect">Indirect (Different product, same need)</option>
                  <option value="substitute">Substitute (Alternative / DIY)</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Offering Description <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="e.g. Enterprise threat detection suite with pricing tier"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Evidence / Verification URL <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.evidence_url}
                  onChange={(e) => setFormData({ ...formData, evidence_url: e.target.value })}
                  placeholder="e.g. https://g2.com/compare/acme-vs-rival"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setEditingCompetitorId(null);
                }}
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
              >
                Cancel
              </button>

              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving Competitor...</span>
                  </>
                ) : (
                  <span>{editingCompetitorId ? 'Update Competitor' : 'Save Competitor'}</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4 space-y-3 shadow-xl">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Tier Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setTierFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tierFilter === 'all'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              All Tiers ({totalCount})
            </button>
            <button
              onClick={() => setTierFilter('direct')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tierFilter === 'direct'
                  ? 'bg-rose-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-rose-300 border border-slate-800'
              }`}
            >
              Direct ({directCount})
            </button>
            <button
              onClick={() => setTierFilter('indirect')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tierFilter === 'indirect'
                  ? 'bg-amber-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-amber-300 border border-slate-800'
              }`}
            >
              Indirect ({indirectCount})
            </button>
            <button
              onClick={() => setTierFilter('substitute')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                tierFilter === 'substitute'
                  ? 'bg-violet-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-violet-300 border border-slate-800'
              }`}
            >
              Substitute ({substituteCount})
            </button>
          </div>

          {/* Status Dropdown & Search Bar */}
          <div className="flex items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="all">Status: All</option>
              <option value="active">Active Only</option>
              <option value="inactive">Deactivated Only</option>
            </select>

            <div className="relative min-w-[200px]">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search competitors..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>
        </div>
      </div>

      {/* Competitors Grouped by Tier */}
      <div className="space-y-6">
        {isLoading && competitors.length === 0 ? (
          <div className="py-16 text-center text-xs text-slate-400 space-y-3">
            <RefreshCw className="w-6 h-6 mx-auto animate-spin text-indigo-400" />
            <p>Loading competitor intelligence...</p>
          </div>
        ) : filteredCompetitors.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
              <Users2 className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h4 className="text-base font-bold text-white tracking-tight">
                {competitors.length === 0 ? 'No Competitors Mapped Yet' : 'No Competitors Match Current Filter'}
              </h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                {competitors.length === 0
                  ? 'Add your first competitor manually or click "Discover with AI" to generate suggestions from the company profile.'
                  : 'Try selecting "All Tiers" or clearing your search term.'}
              </p>
            </div>
            {competitors.length === 0 && (
              <div className="pt-2 flex items-center justify-center gap-3">
                <button
                  onClick={handleDiscoverCompetitors}
                  disabled={isDiscovering}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 shadow-md transition-all"
                >
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Discover with AI</span>
                </button>
                <button
                  onClick={handleOpenAddForm}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition-all"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>Add Manually</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          TIERS.map((tier) => {
            const list = groupedCompetitors[tier.id] || [];
            if (tierFilter !== 'all' && tierFilter !== tier.id) return null;
            if (list.length === 0 && tierFilter !== tier.id) return null;

            const TierIcon = tier.icon;

            return (
              <div key={tier.id} className="space-y-3">
                {/* Tier Section Header */}
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    <TierIcon className={`w-4 h-4 ${tier.color}`} />
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                      {tier.label}
                    </h3>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-semibold">
                      {list.length}
                    </span>
                  </div>
                  <span className="text-xs text-slate-400 hidden sm:inline">{tier.desc}</span>
                </div>

                {/* Cards Grid */}
                {list.length === 0 ? (
                  <p className="text-xs text-slate-500 italic py-2">
                    No {tier.label.toLowerCase()} mapped.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => {
                      const isActive = c.is_active;
                      const isToggling = togglingId === c.id;

                      return (
                        <div
                          key={c.id}
                          className={`rounded-2xl bg-slate-900 border transition-all p-5 shadow-xl flex flex-col justify-between space-y-4 group hover:border-slate-700 ${
                            !isActive ? 'opacity-70 bg-slate-900/60 border-slate-800/60' : 'border-slate-800'
                          }`}
                        >
                          <div className="space-y-2">
                            {/* Card Top: Tier Badge + Verification Status + Active Toggle */}
                            <div className="flex items-center justify-between gap-1">
                              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${tier.badge}`}>
                                {c.competitor_type}
                              </span>

                              <div className="flex items-center gap-1.5">
                                {c.evidence_url ? (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-950/60 border border-emerald-900 px-2 py-0.5 rounded-md">
                                    <ShieldCheck className="w-3 h-3 text-emerald-400" />
                                    <span>Verified</span>
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-400 bg-amber-950/60 border border-amber-900 px-2 py-0.5 rounded-md">
                                    <ShieldAlert className="w-3 h-3 text-amber-400" />
                                    <span>Unverified</span>
                                  </span>
                                )}

                                <button
                                  onClick={() => handleToggleActive(c)}
                                  disabled={isToggling}
                                  className={`p-1 rounded-md transition-colors ${
                                    isActive
                                      ? 'text-slate-400 hover:text-rose-400 hover:bg-rose-950/40'
                                      : 'text-slate-400 hover:text-emerald-400 hover:bg-emerald-950/40'
                                  }`}
                                  title={isActive ? 'Deactivate competitor' : 'Reactivate competitor'}
                                >
                                  <Power className={`w-3.5 h-3.5 ${isToggling ? 'animate-spin text-cyan-400' : ''}`} />
                                </button>

                                <button
                                  onClick={() => handleOpenEditForm(c)}
                                  className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                                  title="Edit competitor"
                                >
                                  <Edit3 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>

                            {/* Name & Website */}
                            <div>
                              <h4 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors">
                                {c.name}
                              </h4>
                              {c.website_url && (
                                <div className="flex items-center gap-1 text-xs text-cyan-400 font-mono mt-0.5 truncate">
                                  <a
                                    href={c.website_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="hover:underline truncate"
                                  >
                                    {c.website_url}
                                  </a>
                                  <ExternalLink className="w-3 h-3 flex-shrink-0 opacity-70" />
                                </div>
                              )}
                            </div>

                            {/* Description */}
                            {c.description && (
                              <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
                                {c.description}
                              </p>
                            )}

                            {/* Evidence Link Callout */}
                            {c.evidence_url && (
                              <div className="flex items-center gap-1 text-[11px] text-slate-400 pt-1 truncate">
                                <span className="text-slate-500">Evidence:</span>
                                <a
                                  href={c.evidence_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-indigo-400 hover:underline truncate max-w-[200px]"
                                >
                                  {c.evidence_url}
                                </a>
                                <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                              </div>
                            )}
                          </div>

                          {/* Footer: Status Note */}
                          <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500">
                            <span>Status: <strong className={isActive ? 'text-emerald-400' : 'text-slate-400'}>{isActive ? 'Active' : 'Deactivated'}</strong></span>
                            <span>{new Date(c.created_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                      );
                    })}
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
