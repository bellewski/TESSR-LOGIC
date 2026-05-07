import { useBuilds } from '../hooks/useBuilds'
import BuildSubmitForm from '../components/BuildSubmitForm'
import BuildTable from '../components/BuildTable'
import { RefreshCw } from 'lucide-react'

export default function Dashboard() {
  const { builds, total, loading, error, refetch, createBuild } = useBuilds()

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-200">Dashboard</h1>
          <p className="text-xs text-muted mt-0.5">{total} build{total !== 1 ? 's' : ''} total</p>
        </div>
        <button
          onClick={refetch}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted hover:text-slate-200 border border-surface-600 rounded hover:border-surface-500 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <BuildSubmitForm onSubmit={createBuild} />

      <div className="bg-surface-800 border border-surface-600 rounded-lg p-4">
        <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">Recent Builds</h2>
        {error && (
          <div className="text-xs text-red-400 mb-3">{error}</div>
        )}
        {loading && builds.length === 0 ? (
          <div className="text-center py-8 text-muted text-sm font-mono">Loading...</div>
        ) : (
          <BuildTable builds={builds} />
        )}
      </div>
    </div>
  )
}
