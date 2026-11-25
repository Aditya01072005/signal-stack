import React from 'react';
import { Menu, RefreshCw, Building } from 'lucide-react';

export default function Header({
  activeTabTitle,
  backendStatus,
  isCheckingHealth,
  onCheckHealth,
  companies = [],
  selectedCompany,
  onSelectCompany,
  onOpenMobileSidebar,
}) {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-16 px-4 lg:px-8 bg-slate-900/80 backdrop-blur-md border-b border-slate-800">
      {/* Left: Mobile hamburger + Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobileSidebar}
          className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 focus:outline-none"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <h1 className="text-lg font-semibold text-white tracking-tight">
            {activeTabTitle}
          </h1>
          <p className="text-xs text-slate-400 hidden sm:block">
            Signal Stack Autonomous Executive Intelligence Platform
          </p>
        </div>
      </div>

      {/* Right: Company Selector + Health Status + Refresh */}
      <div className="flex items-center gap-3 sm:gap-4">
        {/* Company Quick-Select */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <select
              value={selectedCompany?.id || ''}
              onChange={(e) => {
                const found = companies.find((c) => String(c.id) === e.target.value);
                onSelectCompany(found || null);
              }}
              className="appearance-none bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg pl-8 pr-8 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-medium cursor-pointer"
            >
              {companies.length === 0 ? (
                <option value="">No companies registered</option>
              ) : (
                <>
                  <option value="">Select target company...</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </>
              )}
            </select>
            <Building className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        {/* Backend Health Badge */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
            backendStatus === 'online'
              ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60'
              : backendStatus === 'checking'
              ? 'bg-amber-950/60 text-amber-400 border-amber-800/60'
              : 'bg-rose-950/60 text-rose-400 border-rose-800/60'
          }`}
          title="Backend API status (/health)"
        >
          <span
            className={`w-2 h-2 rounded-full ${
              backendStatus === 'online'
                ? 'bg-emerald-400 animate-pulse'
                : backendStatus === 'checking'
                ? 'bg-amber-400 animate-ping'
                : 'bg-rose-400'
            }`}
          />
          <span className="hidden md:inline">
            {backendStatus === 'online'
              ? 'Backend Online'
              : backendStatus === 'checking'
              ? 'Checking API...'
              : 'Backend Offline'}
          </span>
          <span className="md:hidden">
            {backendStatus === 'online' ? 'Online' : 'Offline'}
          </span>
        </div>

        {/* Refresh Health Action */}
        <button
          onClick={onCheckHealth}
          disabled={isCheckingHealth}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
          title="Check backend health"
        >
          <RefreshCw
            className={`w-4 h-4 ${isCheckingHealth ? 'animate-spin text-indigo-400' : ''}`}
          />
        </button>
      </div>
    </header>
  );
}
