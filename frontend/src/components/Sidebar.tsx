import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Settings, Cpu, Wand2, FolderOpen, GitBranch, Archive, Wrench, Sun, Moon, Cog, Github } from 'lucide-react'
import { clsx } from 'clsx'
import { useTheme } from '../hooks/useTheme'

const NAV = [
  { to: '/',               label: 'Dashboard',      Icon: LayoutDashboard },
  { to: '/prompt-studio', label: 'Prompt Studio',  Icon: Wand2 },
  { to: '/project-context', label: 'Project Context', Icon: FolderOpen },
  { to: '/pipeline',      label: 'Build Pipeline', Icon: GitBranch },
  { to: '/artifacts',     label: 'Artifacts',      Icon: Archive },
  { to: '/workshop',      label: 'Workshop',       Icon: Wrench },
  { to: '/connectors',    label: 'Connectors',     Icon: Github },
  { to: '/advanced',      label: 'Advanced',       Icon: Cog },
  { to: '/settings',      label: 'Settings',       Icon: Settings },
]

function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      className="p-1.5 rounded hover:bg-surface-700 text-muted hover:text-slate-200 transition-colors"
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}

export default function Sidebar() {
  return (
    <aside className="w-56 flex-shrink-0 bg-surface-800 border-r border-surface-600 flex flex-col">
      <div className="px-4 py-5 border-b border-surface-600">
        <div className="flex items-center gap-2">
          <Cpu className="text-accent-500" size={20} />
          <span className="font-mono font-bold text-sm tracking-widest text-slate-200">TESSR-LOGIC</span>
        </div>
        <p className="text-xs text-muted mt-1">Multi-Agent Build Factory</p>
      </div>

      <nav className="flex-1 px-2 py-4 space-y-0.5">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => clsx(
              'flex items-center gap-2.5 px-3 py-2 rounded text-sm font-medium transition-colors',
              isActive
                ? 'bg-accent-500/15 text-accent-400'
                : 'text-slate-400 hover:text-slate-200 hover:bg-surface-700'
            )}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-surface-600 flex items-center justify-between">
        <p className="text-xs text-muted font-mono">v0.2.0 · local</p>
        <ThemeToggle />
      </div>
    </aside>
  )
}
