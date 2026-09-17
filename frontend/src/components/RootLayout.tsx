import { useState, useEffect } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Activity, BarChart3, Database, Menu, X, Factory } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from './ui/utils';

const navigation = [
  { to: '/', name: 'Dashboard', icon: Activity, end: true },
  { to: '/analytics', name: 'Analytics', icon: BarChart3, end: false },
  { to: '/database', name: 'Database', icon: Database, end: false },
];

export function RootLayout() {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="h-screen bg-[#f4f5f7] flex flex-col overflow-hidden">
      {/* Subtle grid background */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          backgroundImage:
            'linear-gradient(rgba(17,24,39,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(17,24,39,0.04) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      {/* Header */}
      <header className="relative z-50 bg-white border-b border-gray-200 px-6 py-3 shrink-0 shadow-sm">
        <div className="max-w-[1920px] mx-auto flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gray-900 flex items-center justify-center">
              <Factory className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-gray-900">Jeans Factory Monitor</h1>
              <p className="text-xs text-gray-500">Production Floor · Real-time Data</p>
            </div>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex items-center gap-1">
            {navigation.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.to} to={item.to} end={item.end}>
                  {({ isActive }) => (
                    <Button
                      variant="ghost"
                      size="sm"
                      className={cn(
                        'gap-2 transition-all duration-200',
                        isActive
                          ? 'bg-gray-900 text-white hover:bg-gray-800 hover:text-white'
                          : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                      )}
                    >
                      <Icon className="w-4 h-4" />
                      {item.name}
                    </Button>
                  )}
                </NavLink>
              );
            })}
          </nav>

          <div className="flex items-center gap-4">
            {/* Live Indicator */}
            <div className="hidden md:flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <span className="text-xs text-gray-500">Live</span>
            </div>

            {/* Time Display */}
            <div className="hidden md:block text-right">
              <div className="text-xs text-gray-400">
                {currentTime.toLocaleDateString('en-US', {
                  weekday: 'short',
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
              <div className="text-sm text-gray-700 font-mono">
                {currentTime.toLocaleTimeString()}
              </div>
            </div>

            {/* Mobile Menu */}
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden text-gray-700"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav className="lg:hidden mt-4 pt-4 border-t border-gray-200">
            <div className="flex flex-col gap-1">
              {navigation.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink key={item.to} to={item.to} end={item.end}>
                    {({ isActive }) => (
                      <Button
                        variant="ghost"
                        size="sm"
                        className={cn(
                          'w-full justify-start gap-2',
                          isActive
                            ? 'bg-gray-900 text-white'
                            : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                        )}
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        <Icon className="w-4 h-4" />
                        {item.name}
                      </Button>
                    )}
                  </NavLink>
                );
              })}
            </div>
          </nav>
        )}
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex-1 min-h-0 overflow-auto w-full px-6 py-6">
        <div className="max-w-[1920px] mx-auto">
          <Outlet />
        </div>
      </main>

      {/* Footer — always pinned to bottom */}
      <footer className="relative z-50 bg-white border-t border-gray-200 px-6 py-3 shrink-0 print:hidden">
        <div className="max-w-[1920px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-gray-900 flex items-center justify-center">
              <Factory className="w-3 h-3 text-white" />
            </div>
            <span className="text-xs text-gray-600">Smart Efficiency Monitoring System</span>
            <span className="text-gray-300">·</span>
            <span className="text-xs text-gray-400">Jeans Production v2.2.0</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-400">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
            </span>
            <span>System Online</span>
          </div>
        </div>
      </footer>
    </div>
  );
}