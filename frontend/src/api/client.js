/**
 * Signal Stack API Client
 * Configured for communication with the FastAPI backend (http://localhost:8000).
 * In development, Vite proxies requests to http://localhost:8000.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const { headers: optionHeaders, ...fetchOptions } = options;
  const config = {
    ...fetchOptions,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...optionHeaders,
    },
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      let errorDetail = 'API request failed';
      try {
        const errorJson = await response.json();
        if (typeof errorJson.detail === 'string') {
          errorDetail = errorJson.detail;
        } else if (Array.isArray(errorJson.detail)) {
          // FastAPI pydantic validation errors
          errorDetail = errorJson.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
        } else if (typeof errorJson.detail === 'object' && errorJson.detail !== null) {
          // Structured research error
          errorDetail =
            errorJson.detail.scrape_error ||
            errorJson.detail.message ||
            `Scrape status: ${errorJson.detail.scrape_status || 'failed'}`;
        } else {
          errorDetail = errorJson.message || JSON.stringify(errorJson);
        }
      } catch {
        errorDetail = `HTTP ${response.status} ${response.statusText}`;
      }
      const err = new Error(errorDetail);
      err.status = response.status;
      throw err;
    }
    // Return null if 204 No Content
    if (response.status === 204) return null;
    return await response.json();
  } catch (error) {
    console.error(`[API Error] ${options.method || 'GET'} ${url}:`, error.message);
    throw error;
  }
}

export const api = {
  // System Health
  health: {
    check: () => request('/health'),
    root: () => request('/'),
  },

  // Companies
  companies: {
    list: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies${query ? `?${query}` : ''}`);
    },
    get: (id) => request(`/api/v1/companies/${id}`),
    create: (data) => request('/api/v1/companies', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/api/v1/companies/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id) => request(`/api/v1/companies/${id}`, { method: 'DELETE' }),
  },

  // Competitors
  competitors: {
    list: (companyId, params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies/${companyId}/competitors${query ? `?${query}` : ''}`);
    },
    get: (companyId, competitorId) =>
      request(`/api/v1/companies/${companyId}/competitors/${competitorId}`),
    create: (companyId, data) =>
      request(`/api/v1/companies/${companyId}/competitors`, { method: 'POST', body: JSON.stringify(data) }),
    update: (companyId, competitorId, data) =>
      request(`/api/v1/companies/${companyId}/competitors/${competitorId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    deactivate: (companyId, competitorId) =>
      request(`/api/v1/companies/${companyId}/competitors/${competitorId}/deactivate`, { method: 'POST' }),
    discover: (companyId) =>
      request(`/api/v1/companies/${companyId}/competitors/discover`, { method: 'POST' }),
  },

  // Research
  research: {
    trigger: (companyId) =>
      request(`/api/v1/companies/${companyId}/research`, { method: 'POST' }),
  },

  // Sources & Scraping
  sources: {
    list: (companyId, params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies/${companyId}/sources${query ? `?${query}` : ''}`);
    },
    get: (companyId, sourceId) =>
      request(`/api/v1/companies/${companyId}/sources/${sourceId}`),
    create: (companyId, data) =>
      request(`/api/v1/companies/${companyId}/sources`, { method: 'POST', body: JSON.stringify(data) }),
    update: (companyId, sourceId, data) =>
      request(`/api/v1/companies/${companyId}/sources/${sourceId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    deactivate: (companyId, sourceId) =>
      request(`/api/v1/companies/${companyId}/sources/${sourceId}`, { method: 'DELETE' }),
    crawl: (companyId, sourceId) =>
      request(`/api/v1/companies/${companyId}/sources/${sourceId}/crawl`, { method: 'POST' }),
  },

  // Internal company documents
  documents: {
    upload: (companyId, file) => {
      const body = new FormData();
      body.append('file', file);
      return request(`/api/v1/companies/${companyId}/documents`, {
        method: 'POST',
        body,
      });
    },
  },

  // Adaptive Interview
  interview: {
    getActive: (companyId) => request(`/api/v1/companies/${companyId}/interview`),
    start: (companyId) =>
      request(`/api/v1/companies/${companyId}/interview/start`, { method: 'POST' }),
    getInterview: (companyId, interviewId) =>
      request(`/api/v1/companies/${companyId}/interview/${interviewId}`),
    submitAnswer: (companyId, interviewId, data) =>
      request(`/api/v1/companies/${companyId}/interview/${interviewId}/answer`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    editAnswer: (companyId, interviewId, questionId, data) =>
      request(`/api/v1/companies/${companyId}/interview/${interviewId}/questions/${questionId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    list: (companyId) => request(`/api/v1/companies/${companyId}/interviews`),
  },

  // Monitoring Pipeline
  monitoring: {
    trigger: (companyId) =>
      request(`/api/v1/companies/${companyId}/monitoring/run`, { method: 'POST' }),
  },

  // Signals Feed & Analysis
  signals: {
    list: (companyId, params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies/${companyId}/signals${query ? `?${query}` : ''}`);
    },
    listRanked: (companyId, params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies/${companyId}/signals/ranked${query ? `?${query}` : ''}`);
    },
    analyze: (companyId, signalId) =>
      request(`/api/v1/companies/${companyId}/signals/${signalId}/analyze`, { method: 'POST' }),
  },

  // Briefs (Monday Morning Brief)
  briefs: {
    list: (companyId, params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/api/v1/companies/${companyId}/briefs${query ? `?${query}` : ''}`);
    },
    getCurrent: (companyId) =>
      request(`/api/v1/companies/${companyId}/briefs/current`),
    get: (companyId, briefId) =>
      request(`/api/v1/companies/${companyId}/briefs/${briefId}`),
    generate: (companyId) =>
      request(`/api/v1/companies/${companyId}/briefs/generate`, { method: 'POST' }),
  },

  // Scheduler & Automation
  scheduler: {
    getStatus: () => request('/api/v1/scheduler/status'),
    runWeeklyBriefs: () =>
      request('/api/v1/scheduler/jobs/weekly-briefs/run', { method: 'POST' }),
    runMonthlySourceHealthAudit: () =>
      request('/api/v1/scheduler/jobs/monthly-source-health-audit/run', { method: 'POST' }),
  },
};

export default api;
