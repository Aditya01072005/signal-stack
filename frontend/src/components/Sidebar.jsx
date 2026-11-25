import React from 'react';
import {
  LayoutDashboard,
  Building2,
  Users2,
  MessageSquareText,
  Radio,
  Radar,
  FileText,
  Clock,
  Cpu,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, badge: null },
  { id: 'companies', label: 'Companies & Intel', icon: Building2, badge: 'Core' },
  { id: 'competitors', label: 'Competitor Intel', icon: Users2, badge: '3-Tier' },
  { id: 'interview', label: 'Adaptive Interview', icon: MessageSquareText, badge: 'AI' },
  { id: 'sources', label: 'Ethical Sources', icon: Radio, badge: null },
  { id: 'signals', label: 'Signal Radar', icon: Radar, badge: null },
  { id: 'briefs', label: 'Executive Briefs', icon: FileText, badge: '10-Sec' },
  { id: 'scheduler', label: 'Scheduler & Health', icon: Clock, badge: null },
];

export default function Sidebar({
  activeTab,
  onSelectTab,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}) {
  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 flex flex-col bg-slate-900 border-r border-slate-800 transition-all duration-300 ${
          collapsed ? 'w-20' : 'w-64'
        } ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Brand Header */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-slate-800">
          {!collapsed ? (
            <div className="flex items-center space-x-3 overflow-hidden">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20 flex-shrink-0">
                <Radar className="w-5 h-5 animate-pulse" />
              </div>
              <div className="truncate">
                <span className="font-bold tracking-tight text-white text-base block">
                  SIGNAL STACK
                </span>
                <span className="text-[10px] text-cyan-400 font-medium tracking-wider uppercase block">
                  Executive Engine
                </span>
              </div>
            </div>
          ) : (
            <div className="mx-auto w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
              <Radar className="w-5 h-5" />
            </div>
          )}

          {/* Desktop Collapse Toggle */}
          <button
            onClick={onToggleCollapse}
            className="hidden lg:flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation Links */}
        <div className="flex-1 py-4 px-3 space-y-1.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => {
                  onSelectTab(item.id);
                  if (onCloseMobile) onCloseMobile();
                }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group relative ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                } ${collapsed ? 'justify-center px-0' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <Icon
                  className={`w-5 h-5 flex-shrink-0 transition-transform group-hover:scale-110 ${
                    isActive ? 'text-white' : 'text-slate-400 group-hover:text-indigo-400'
                  }`}
                />
                {!collapsed && (
                  <>
                    <span className="truncate flex-1 text-left">{item.label}</span>
                    {item.badge && (
                      <span
                        className={`text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded tracking-wide ${
                          isActive
                            ? 'bg-white/20 text-white'
                            : 'bg-slate-800 text-slate-300 border border-slate-700'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </>
                )}

                {/* Collapsed Active Indicator */}
                {collapsed && isActive && (
                  <span className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-cyan-400 rounded-l" />
                )}
              </button>
            );
          })}
        </div>

        {/* Model & Backend Status Footnote */}
        <div className="p-3 border-t border-slate-800 bg-slate-900/50">
          {!collapsed ? (
            <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/50 text-xs">
              <div className="flex items-center gap-2 text-slate-300 font-medium mb-1">
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                <span>Ollama Engine</span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono truncate">llama3.2:3b</p>
              <div className="mt-2 flex items-center gap-1.5 text-[11px] text-emerald-400">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Local & Private</span>
              </div>
            </div>
          ) : (
            <div className="flex justify-center" title="Ollama llama3.2:3b Local Engine">
              <Cpu className="w-5 h-5 text-cyan-400" />
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
