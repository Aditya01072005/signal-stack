import React, { useState, useEffect, useCallback } from 'react';
import {
  Radio,
  PlusCircle,
  ExternalLink,
  RefreshCw,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Building2,
  Edit3,
  Power,
  Play,
  HeartPulse,
  Clock,
  ShieldCheck,
  ShieldAlert,
  X,
  Layers,
  FileText,
  Upload,
} from 'lucide-react';
import api from '../api/client';

const CATEGORIES = ['Customers', 'Competitors', 'Market', 'Internal'];

export default function SourceManager({ selectedCompany }) {
  // Sources data
  const [sources, setSources] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Filters & Search
  const [selectedCategory, setSelectedCategory] = useState('all'); // 'all' | 'Customers' | 'Competitors' | 'Market' | 'Internal'
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'active' | 'inactive' | 'unhealthy'
  const [searchQuery, setSearchQuery] = useState('');

  // Form State (for both Add and Edit)
  const [showForm, setShowForm] = useState(false);
  const [editingSourceId, setEditingSourceId] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    url: '',
    category: 'Competitors',
    description: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  // Per-source action loading states
  const [crawlingSourceId, setCrawlingSourceId] = useState(null);
  const [togglingSourceId, setTogglingSourceId] = useState(null);
  const [latestCrawlResult, setLatestCrawlResult] = useState(null);
  const [documentFile, setDocumentFile] = useState(null);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const [documentMessage, setDocumentMessage] = useState(null);

  // Load sources for selected company (including inactive ones)
  const loadSources = useCallback(async () => {
    if (!selectedCompany?.id) return;

    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.sources.list(selectedCompany.id, {
        include_inactive: true,
        limit: 100,
      });
      const items = res?.items || (Array.isArray(res) ? res : []);
      setSources(items);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load company sources.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCompany]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const handleDocumentUpload = async (e) => {
    e.preventDefault();
    if (!selectedCompany?.id || !documentFile) return;

    if (documentFile.size > 10 * 1024 * 1024) {
      setDocumentMessage({ error: 'Documents must be 10 MB or smaller.' });
      return;
    }

    const form = e.currentTarget;
    setIsUploadingDocument(true);
    setDocumentMessage(null);
    try {
      const result = await api.documents.upload(selectedCompany.id, documentFile);
      setDocumentMessage({
        success: `${result.filename} stored with ${result.extracted_characters.toLocaleString()} characters and an evidence-linked signal.`,
      });
      setDocumentFile(null);
      form.reset();
    } catch (err) {
      setDocumentMessage({ error: err.message || 'Document upload failed.' });
    } finally {
      setIsUploadingDocument(false);
    }
  };

  // Open Form for Adding New Source
  const handleOpenAddForm = () => {
    setEditingSourceId(null);
    setFormData({
      name: '',
      url: '',
      category: 'Competitors',
      description: '',
    });
    setFormError(null);
    setShowForm(true);
  };

  // Open Form for Editing Existing Source
  const handleOpenEditForm = (src) => {
    setEditingSourceId(src.id);
    setFormData({
      name: src.name,
      url: src.url,
      category: src.category,
      description: src.description || '',
    });
    setFormError(null);
    setShowForm(true);
  };

  // Submit Add or Edit Source
  const handleSubmitForm = async (e) => {
    e.preventDefault();
    if (!selectedCompany?.id) return;

    const name = formData.name.trim();
    let url = formData.url.trim();
    const category = formData.category;
    const description = formData.description.trim() || undefined;

    if (!name) {
      setFormError('Source name is required.');
      return;
    }
    if (!url) {
      setFormError('Source URL is required.');
      return;
    }
    if (!url.toLowerCase().startsWith('http://') && !url.toLowerCase().startsWith('https://')) {
      url = `https://${url}`;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      if (editingSourceId) {
        // Edit existing source
        const updated = await api.sources.update(selectedCompany.id, editingSourceId, {
          name,
          url,
          category,
          description,
        });
        setSources((prev) =>
          prev.map((s) => (s.id === editingSourceId ? updated : s))
        );
        setSuccessMessage(`Source "${updated.name}" updated successfully.`);
      } else {
        // Create new source
        const created = await api.sources.create(selectedCompany.id, {
          name,
          url,
          category,
          description,
        });
        setSources((prev) => [created, ...prev]);
        setSuccessMessage(`Source "${created.name}" registered successfully.`);
      }

      setShowForm(false);
      setEditingSourceId(null);
    } catch (err) {
      setFormError(err.message || 'Failed to save source.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle active/inactive status
  const handleToggleStatus = async (src) => {
    if (!selectedCompany?.id) return;

    setTogglingSourceId(src.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      if (src.status === 'active') {
        // Deactivate
        await api.sources.deactivate(selectedCompany.id, src.id);
        setSources((prev) =>
          prev.map((s) => (s.id === src.id ? { ...s, status: 'inactive' } : s))
        );
        setSuccessMessage(`Source "${src.name}" has been deactivated.`);
      } else {
        // Reactivate
        const updated = await api.sources.update(selectedCompany.id, src.id, {
          active: true,
        });
        setSources((prev) =>
          prev.map((s) => (s.id === src.id ? updated : s))
        );
        setSuccessMessage(`Source "${src.name}" has been reactivated.`);
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to change source status.');
    } finally {
      setTogglingSourceId(null);
    }
  };

  // Crawl individual source
  const handleCrawlNow = async (src) => {
    if (!selectedCompany?.id) return;

    setCrawlingSourceId(src.id);
    setErrorMessage(null);
    setLatestCrawlResult(null);
    try {
      const crawlRes = await api.sources.crawl(selectedCompany.id, src.id);
      setLatestCrawlResult(crawlRes);

      // Refresh source list to show updated last_crawled_at, health_score, etc.
      await loadSources();

      if (crawlRes.crawl_status === 'success') {
        setSuccessMessage(`Crawl successful for "${src.name}": ${crawlRes.characters_scraped || 0} characters extracted.`);
      } else {
        setErrorMessage(`Crawl ${crawlRes.crawl_status} for "${src.name}": ${crawlRes.message}`);
      }
    } catch (err) {
      setErrorMessage(err.message || `Crawl request failed for "${src.name}".`);
    } finally {
      setCrawlingSourceId(null);
    }
  };

  // Filter calculations
  const totalCount = sources.length;
  const activeCount = sources.filter((s) => s.status === 'active').length;
  const inactiveCount = sources.filter((s) => s.status === 'inactive' || s.status === 'dead').length;
  const unhealthyCount = sources.filter((s) => (s.health_score ?? 100) < 80 || s.consecutive_failures > 0).length;

  const filteredSources = sources.filter((s) => {
    // Category filter
    if (selectedCategory !== 'all' && s.category !== selectedCategory) return false;

    // Status filter
    if (statusFilter === 'active' && s.status !== 'active') return false;
    if (statusFilter === 'inactive' && s.status === 'active') return false;
    if (statusFilter === 'unhealthy' && (s.health_score ?? 100) >= 80 && s.consecutive_failures === 0) return false;

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = s.name?.toLowerCase().includes(q);
      const matchUrl = s.url?.toLowerCase().includes(q);
      const matchDesc = s.description?.toLowerCase().includes(q);
      if (!matchName && !matchUrl && !matchDesc) return false;
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
          Select a registered company from the header dropdown or the Company Setup page to manage its web scraping sources.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Radio className="w-6 h-6 text-indigo-400" />
            <span>Ethical Source Manager</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Configure target monitoring domains, enforce robots.txt compliance, and trigger on-demand scraping.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start md:self-auto">
          <button
            onClick={handleOpenAddForm}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all hover:scale-[1.02]"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Register New Source</span>
          </button>

          <button
            onClick={loadSources}
            disabled={isLoading}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Refresh sources"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      <form
        onSubmit={handleDocumentUpload}
        className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-3"
      >
        <div className="flex items-center gap-2 text-white font-semibold">
          <FileText className="w-4 h-4 text-cyan-400" />
          <h3>Internal Documents for {selectedCompany.name}</h3>
        </div>
        <p className="text-xs text-slate-400">
          Upload PDF, CSV, or TXT files (up to 10 MB). Extracted content is stored privately and linked to a company-specific signal.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="file"
            accept=".pdf,.csv,.txt,application/pdf,text/csv,text/plain"
            onChange={(e) => setDocumentFile(e.target.files?.[0] || null)}
            className="min-w-0 flex-1 text-xs text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-slate-200"
          />
          <button
            type="submit"
            disabled={!documentFile || isUploadingDocument}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-700 px-4 py-2 text-xs font-semibold text-white hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Upload className="w-4 h-4" />
            {isUploadingDocument ? 'Uploading…' : 'Upload Document'}
          </button>
        </div>
        {documentMessage?.success && (
          <p role="status" className="text-xs text-emerald-300">{documentMessage.success}</p>
        )}
        {documentMessage?.error && (
          <p role="alert" className="text-xs text-rose-300">{documentMessage.error}</p>
        )}
      </form>

      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Configured Sources</p>
            <p className="text-xl font-bold text-white mt-0.5">{totalCount}</p>
          </div>
          <Layers className="w-5 h-5 text-indigo-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-emerald-400 font-medium">Active Monitored</p>
            <p className="text-xl font-bold text-emerald-300 mt-0.5">{activeCount}</p>
          </div>
          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Deactivated</p>
            <p className="text-xl font-bold text-slate-300 mt-0.5">{inactiveCount}</p>
          </div>
          <Power className="w-5 h-5 text-slate-500" />
        </div>

        <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-amber-400 font-medium">Health Warning</p>
            <p className="text-xl font-bold text-amber-300 mt-0.5">{unhealthyCount}</p>
          </div>
          <HeartPulse className="w-5 h-5 text-amber-400" />
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
              <span className="font-semibold block text-rose-200">Source Manager Notice</span>
              <p className="mt-0.5 leading-relaxed">{errorMessage}</p>
            </div>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Crawl Result Toast/Banner */}
      {latestCrawlResult && (
        <div
          className={`p-4 rounded-xl border text-xs shadow-lg flex items-start justify-between gap-3 ${
            latestCrawlResult.crawl_status === 'success'
              ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
              : latestCrawlResult.crawl_status === 'blocked'
              ? 'bg-amber-950/60 border-amber-800 text-amber-300'
              : 'bg-rose-950/60 border-rose-800 text-rose-300'
          }`}
        >
          <div className="flex items-start gap-2.5">
            {latestCrawlResult.crawl_status === 'success' ? (
              <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
            ) : latestCrawlResult.crawl_status === 'blocked' ? (
              <ShieldAlert className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            )}
            <div>
              <p className="font-bold uppercase tracking-wider text-[11px]">
                Crawl Status: {latestCrawlResult.crawl_status}
              </p>
              <p className="mt-0.5 leading-relaxed">{latestCrawlResult.message}</p>
              {latestCrawlResult.characters_scraped != null && (
                <p className="text-[11px] font-mono text-slate-400 mt-1">
                  Extracted {latestCrawlResult.characters_scraped.toLocaleString()} clean characters
                </p>
              )}
            </div>
          </div>
          <button onClick={() => setLatestCrawlResult(null)} className="text-slate-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Add / Edit Source Modal/Drawer */}
      {showForm && (
        <div className="rounded-2xl bg-slate-900 border border-indigo-500/50 p-6 shadow-2xl relative overflow-hidden space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Radio className="w-4 h-4 text-indigo-400" />
              <span>{editingSourceId ? 'Edit Source Details' : 'Register New Intelligence Source'}</span>
            </h3>
            <button
              onClick={() => {
                setShowForm(false);
                setEditingSourceId(null);
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Source Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Acme Pricing Page or TechCrunch Feed"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Target URL <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  placeholder="e.g. https://example.com/pricing"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Intelligence Quadrant / Category <span className="text-rose-400">*</span>
                </label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Justification / Strategic Purpose <span className="text-slate-500">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="e.g. Monitor competitor tier pricing and feature gates"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setEditingSourceId(null);
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
                    <span>Saving Source...</span>
                  </>
                ) : (
                  <span>{editingSourceId ? 'Update Source' : 'Register Source'}</span>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4 space-y-3 shadow-xl">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Category Tabs */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedCategory === 'all'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              All Categories
            </button>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white shadow'
                    : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {cat}
              </button>
            ))}
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
              <option value="inactive">Inactive Only</option>
              <option value="unhealthy">Health Warnings</option>
            </select>

            <div className="relative min-w-[200px]">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search sources..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            </div>
          </div>
        </div>
      </div>

      {/* Sources List */}
      <div className="space-y-4">
        {isLoading && sources.length === 0 ? (
          <div className="py-16 text-center text-xs text-slate-400 space-y-3">
            <RefreshCw className="w-6 h-6 mx-auto animate-spin text-indigo-400" />
            <p>Loading registered sources...</p>
          </div>
        ) : filteredSources.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center space-y-4">
            <div className="w-12 h-12 mx-auto rounded-xl bg-slate-800 flex items-center justify-center text-slate-400">
              <Radio className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h4 className="text-base font-bold text-white tracking-tight">
                {sources.length === 0 ? 'No Sources Registered Yet' : 'No Sources Match Current Filter'}
              </h4>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                {sources.length === 0
                  ? 'Add your first target intelligence source (e.g. competitor website, pricing table, news portal) to enable autonomous monitoring.'
                  : 'Try selecting "All Categories" or clearing the search bar.'}
              </p>
            </div>
            {sources.length === 0 && (
              <button
                onClick={handleOpenAddForm}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md transition-all"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                <span>Register First Source</span>
              </button>
            )}
          </div>
        ) : (
          filteredSources.map((src) => {
            const isActive = src.status === 'active';
            const isCrawling = crawlingSourceId === src.id;
            const isToggling = togglingSourceId === src.id;
            const health = src.health_score ?? 100;

            // Formatted last crawled date
            const lastCrawledStr = src.last_crawled_at
              ? new Date(src.last_crawled_at).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : 'Never crawled';

            // Category tag color
            const catColors = {
              Customers: 'bg-emerald-950/80 text-emerald-300 border-emerald-800',
              Competitors: 'bg-rose-950/80 text-rose-300 border-rose-800',
              Market: 'bg-cyan-950/80 text-cyan-300 border-cyan-800',
              Internal: 'bg-violet-950/80 text-violet-300 border-violet-800',
            };

            return (
              <div
                key={src.id}
                className={`rounded-2xl bg-slate-900 border transition-all p-5 shadow-xl space-y-4 group hover:border-slate-700 ${
                  !isActive ? 'opacity-70 bg-slate-900/60 border-slate-800/60' : 'border-slate-800'
                }`}
              >
                {/* Header Row */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Category Tag */}
                    <span
                      className={`text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${
                        catColors[src.category] || 'bg-slate-800 text-slate-300 border-slate-700'
                      }`}
                    >
                      {src.category}
                    </span>

                    {/* Status Tag */}
                    <span
                      className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border flex items-center gap-1 ${
                        isActive
                          ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                          : 'bg-slate-800 text-slate-400 border-slate-700'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                      <span>{src.status.toUpperCase()}</span>
                    </span>

                    {/* Health Score Pill */}
                    <div
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${
                        health >= 80
                          ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800/60'
                          : health >= 50
                          ? 'bg-amber-950/40 text-amber-400 border-amber-800/60'
                          : 'bg-rose-950/40 text-rose-400 border-rose-800/60'
                      }`}
                      title={`Health: ${health}% | Consecutive failures: ${src.consecutive_failures}`}
                    >
                      <HeartPulse className="w-3 h-3" />
                      <span>Health: {health}%</span>
                    </div>

                    {src.consecutive_failures > 0 && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
                        {src.consecutive_failures} failures
                      </span>
                    )}
                  </div>

                  {/* Actions: Crawl Now, Edit, Activate/Deactivate */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleCrawlNow(src)}
                      disabled={isCrawling || !isActive}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                      title={isActive ? 'Fetch latest content now' : 'Source is inactive'}
                    >
                      <Play className={`w-3 h-3 ${isCrawling ? 'animate-spin' : ''}`} />
                      <span>{isCrawling ? 'Crawling...' : 'Crawl Now'}</span>
                    </button>

                    <button
                      onClick={() => handleOpenEditForm(src)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                      title="Edit source details"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>

                    <button
                      onClick={() => handleToggleStatus(src)}
                      disabled={isToggling}
                      className={`p-1.5 rounded-lg transition-colors ${
                        isActive
                          ? 'text-slate-400 hover:text-rose-400 hover:bg-rose-950/40'
                          : 'text-slate-400 hover:text-emerald-400 hover:bg-emerald-950/40'
                      }`}
                      title={isActive ? 'Deactivate source' : 'Reactivate source'}
                    >
                      <Power className={`w-4 h-4 ${isToggling ? 'animate-spin text-cyan-400' : ''}`} />
                    </button>
                  </div>
                </div>

                {/* Source Title & Link */}
                <div className="space-y-1">
                  <h3 className="text-base font-bold text-white group-hover:text-indigo-300 transition-colors">
                    {src.name}
                  </h3>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 hover:underline truncate max-w-xl"
                    >
                      {src.url}
                    </a>
                    <ExternalLink className="w-3 h-3 flex-shrink-0 opacity-70" />
                  </div>
                </div>

                {/* Description / Justification */}
                {src.description && (
                  <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">
                    {src.description}
                  </p>
                )}

                {/* Error Banner (if last crawl failed) */}
                {src.last_error_message && (
                  <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-900/60 text-xs text-rose-300 flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block text-rose-200">Last Crawl Error:</span>
                      <p className="mt-0.5">{src.last_error_message}</p>
                    </div>
                  </div>
                )}

                {/* Footer Metadata */}
                <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
                  <div className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span>Last Crawl: <strong className="text-slate-300">{lastCrawledStr}</strong></span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span>Source Type: <span className="font-mono text-slate-300">{src.source_type}</span></span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
