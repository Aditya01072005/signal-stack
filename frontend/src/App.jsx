import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Overview from './components/Overview';
import CompanySetup from './components/CompanySetup';
import CompetitorIntelligence from './components/CompetitorIntelligence';
import AdaptiveInterview from './components/AdaptiveInterview';
import IntelligenceFeed from './components/IntelligenceFeed';
import SourceManager from './components/SourceManager';
import ExecutiveBrief from './components/ExecutiveBrief';
import SchedulerHealth from './components/SchedulerHealth';
import api from './api/client';

const TAB_TITLES = {
  overview: 'Executive Dashboard Overview',
  companies: 'Company Registration & Baseline Intelligence',
  competitors: 'Competitor Intelligence & Tier Mapping',
  interview: 'Adaptive 10-Question AI Interview',
  sources: 'Ethical Sources & Scraping Management',
  signals: 'Signal Detection & Competitor Intelligence Radar',
  briefs: 'Monday Morning Executive Briefs',
  scheduler: 'Weekly Scheduler & Source Health Audits',
};

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Backend Health & Company State
  const [backendStatus, setBackendStatus] = useState('checking'); // 'online' | 'offline' | 'checking'
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [isLoadingCompanies, setIsLoadingCompanies] = useState(false);

  // Check Backend Health
  // isManual: true on explicit user refresh (shows button spinner)
  // isManual: false for silent periodic 30s background polling (avoids UI flicker/re-renders)
  const checkHealth = useCallback(async (isManual = false) => {
    if (isManual) {
      setIsCheckingHealth(true);
    }
    try {
      await api.health.check();
      setBackendStatus('online');
    } catch {
      setBackendStatus('offline');
    } finally {
      if (isManual) {
        setIsCheckingHealth(false);
      }
    }
  }, []);

  // Fetch Companies — stabilized using functional state updates to eliminate unnecessary re-renders
  const loadCompanies = useCallback(async (selectTargetId = null) => {
    setIsLoadingCompanies(true);
    try {
      const data = await api.companies.list({ limit: 100 });
      const list = data?.items || (Array.isArray(data) ? data : []);
      setCompanies(list);

      setSelectedCompany((prev) => {
        if (selectTargetId) {
          const target = list.find((c) => String(c.id) === String(selectTargetId));
          return target || prev;
        }
        if (!prev && list.length > 0) {
          return list[0];
        }
        if (prev) {
          const stillExists = list.find((c) => String(c.id) === String(prev.id));
          return stillExists || (list.length > 0 ? list[0] : null);
        }
        return null;
      });
    } catch {
      // Backend may be offline initially, silent fallback
    } finally {
      setIsLoadingCompanies(false);
    }
  }, []);

  useEffect(() => {
    // Initial load
    checkHealth(false);
    loadCompanies();

    // Stable 30-second periodic background health check
    const healthIntervalId = setInterval(() => {
      checkHealth(false);
    }, 30000);

    return () => clearInterval(healthIntervalId);
  }, [checkHealth, loadCompanies]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col transition-all duration-300 ${
          sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-64'
        }`}
      >
        {/* Sticky Header */}
        <Header
          activeTabTitle={TAB_TITLES[activeTab] || 'Dashboard'}
          backendStatus={backendStatus}
          isCheckingHealth={isCheckingHealth}
          onCheckHealth={() => checkHealth(true)}
          companies={companies}
          selectedCompany={selectedCompany}
          onSelectCompany={setSelectedCompany}
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
        />

        {/* View Content */}
        <main className="flex-1 p-4 lg:p-8">
          {activeTab === 'overview' && (
            <Overview
              onNavigate={setActiveTab}
              backendStatus={backendStatus}
              selectedCompany={selectedCompany}
              companies={companies}
            />
          )}

          {activeTab === 'companies' && (
            <CompanySetup
              companies={companies}
              selectedCompany={selectedCompany}
              onSelectCompany={setSelectedCompany}
              onCompanyCreated={async (newCompany) => {
                await loadCompanies(newCompany.id);
                setSelectedCompany(newCompany);
              }}
              isLoadingCompanies={isLoadingCompanies}
              onRefreshCompanies={() => loadCompanies()}
            />
          )}

          {activeTab === 'competitors' && (
            <CompetitorIntelligence
              selectedCompany={selectedCompany}
              onNavigate={setActiveTab}
            />
          )}

          {activeTab === 'interview' && (
            <AdaptiveInterview
              selectedCompany={selectedCompany}
              onNavigate={setActiveTab}
            />
          )}

          {activeTab === 'sources' && (
            <SourceManager selectedCompany={selectedCompany} />
          )}

          {activeTab === 'signals' && (
            <IntelligenceFeed selectedCompany={selectedCompany} />
          )}

          {activeTab === 'briefs' && (
            <ExecutiveBrief selectedCompany={selectedCompany} />
          )}

          {activeTab === 'scheduler' && (
            <SchedulerHealth
              backendStatus={backendStatus}
              onRefreshHealth={() => checkHealth(true)}
            />
          )}
        </main>
      </div>
    </div>
  );
}
