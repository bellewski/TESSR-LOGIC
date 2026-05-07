import { useState, useEffect } from 'react'
import api from '../api/client'

interface AgentConfig {
  id: string
  name: string
  agent_type: string
  description: string | null
  system_prompt: string | null
  user_prompt_template: string | null
  position: number
  enabled: boolean
  is_builtin: boolean
  input_schema: string | null
  output_schema: string | null
  created_at: string
  updated_at: string
}

interface HireRecommendation {
  recommended_position: number
  rationale: string
  placement: string
  confidence: string
}

export default function Advanced() {
  const [agents, setAgents] = useState<AgentConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'pipeline' | 'prompts' | 'add'>('pipeline')
  const [editingAgent, setEditingAgent] = useState<AgentConfig | null>(null)
  const [editPrompt, setEditPrompt] = useState('')
  const [saving, setSaving] = useState(false)

  // Add agent form state
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newSystemPrompt, setNewSystemPrompt] = useState('')
  const [newPosition, setNewPosition] = useState('')
  const [recommendation, setRecommendation] = useState<HireRecommendation | null>(null)
  const [hiringLoading, setHiringLoading] = useState(false)

  const fetchAgents = async () => {
    setLoading(true)
    try {
      const res = await api.get('/agents')
      setAgents(res.data as AgentConfig[])
      setError('')
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAgents()
  }, [])

  const updatePrompt = async (agentId: string) => {
    setSaving(true)
    try {
      await api.patch(`/agents/${agentId}`, { system_prompt: editPrompt })
      setEditingAgent(null)
      setEditPrompt('')
      fetchAgents()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async (agent: AgentConfig) => {
    try {
      await api.patch(`/agents/${agent.id}`, { enabled: !agent.enabled })
      fetchAgents()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  const consultHiringManager = async () => {
    if (!newName || !newType || !newDesc) {
      setError('Please fill in Name, Type, and Description before consulting the Hiring Manager.')
      return
    }
    setHiringLoading(true)
    setRecommendation(null)
    try {
      const res = await api.post('/agents/hire', {
        new_agent_name: newName,
        new_agent_type: newType,
        new_agent_description: newDesc,
      })
      const data = res.data as HireRecommendation & { success: boolean; error?: string }
      if (data.success) {
        setRecommendation(data)
        setNewPosition(String(data.recommended_position))
        setError('')
      } else {
        setError(data.error || 'Hiring Manager could not recommend placement.')
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setHiringLoading(false)
    }
  }

  const createAgent = async () => {
    if (!newName || !newType) {
      setError('Name and Type are required.')
      return
    }
    setSaving(true)
    try {
      await api.post('/agents', {
        name: newName,
        agent_type: newType,
        description: newDesc || null,
        system_prompt: newSystemPrompt || null,
        position: Number(newPosition) || 99,
        enabled: true,
      })
      setNewName('')
      setNewType('')
      setNewDesc('')
      setNewSystemPrompt('')
      setNewPosition('')
      setRecommendation(null)
      setActiveTab('pipeline')
      fetchAgents()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteAgent = async (agentId: string) => {
    if (!confirm('Delete this agent?')) return
    try {
      await api.delete(`/agents/${agentId}`)
      fetchAgents()
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  const builtinOrder = [
    'hiring_manager',
    'architect',
    'coder',
    'hardener',
    'validator',
    'builder',
    'smoke_tester',
  ]

  const sortedAgents = [...agents].sort((a, b) => {
    const ai = builtinOrder.indexOf(a.agent_type)
    const bi = builtinOrder.indexOf(b.agent_type)
    if (ai !== -1 && bi !== -1) return ai - bi
    if (ai !== -1) return -1
    if (bi !== -1) return 1
    return a.position - b.position
  })

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Advanced</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Manage pipeline agents, edit prompts, and add custom agents.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="flex gap-2 mb-6">
        {(['pipeline', 'prompts', 'add'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setError(''); setRecommendation(null); }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              activeTab === tab
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            {tab === 'pipeline' && 'Pipeline'}
            {tab === 'prompts' && 'Agent Prompts'}
            {tab === 'add' && 'Add Custom Agent'}
          </button>
        ))}
      </div>

      {activeTab === 'pipeline' && (
        <div className="space-y-3">
          {loading ? (
            <div className="text-sm text-gray-500">Loading agents...</div>
          ) : (
            sortedAgents.map((agent) => (
              <div
                key={agent.id}
                className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-xs font-bold text-blue-700 dark:text-blue-300">
                    {agent.position}
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {agent.name}
                      {agent.is_builtin && (
                        <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 px-2 py-0.5 rounded">
                          Built-in
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {agent.agent_type}
                      {agent.description && ` — ${agent.description}`}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => toggleEnabled(agent)}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                      agent.enabled
                        ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400'
                    }`}
                  >
                    {agent.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                  {!agent.is_builtin && (
                    <button
                      onClick={() => deleteAgent(agent.id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Fire
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'prompts' && (
        <div className="space-y-4">
          {loading ? (
            <div className="text-sm text-gray-500">Loading agents...</div>
          ) : (
            sortedAgents.map((agent) => (
              <div
                key={agent.id}
                className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden"
              >
                <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">{agent.name}</div>
                    <div className="text-xs text-gray-500">{agent.agent_type}</div>
                  </div>
                  <button
                    onClick={() => {
                      setEditingAgent(agent)
                      setEditPrompt(agent.system_prompt || '')
                    }}
                    className="px-3 py-1 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/30"
                  >
                    Edit Prompt
                  </button>
                </div>
                {editingAgent?.id === agent.id ? (
                  <div className="p-4">
                    <textarea
                      value={editPrompt}
                      onChange={(e) => setEditPrompt(e.target.value)}
                      rows={12}
                      className="w-full p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-sm font-mono text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none resize-y"
                    />
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() => updatePrompt(agent.id)}
                        disabled={saving}
                        className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                      >
                        {saving ? 'Saving...' : 'Save Prompt'}
                      </button>
                      <button
                        onClick={() => { setEditingAgent(null); setEditPrompt(''); }}
                        className="px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-300 dark:hover:bg-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="p-4">
                    <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto">
                      {agent.system_prompt || '(No custom prompt — using default)'}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'add' && (
        <div className="max-w-2xl space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Agent Name
            </label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. Performance Auditor"
              className="w-full p-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Agent Type
            </label>
            <input
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              placeholder="e.g. performance_auditor"
              className="w-full p-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description
            </label>
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              rows={3}
              placeholder="Describe what this agent does, e.g. 'Analyzes build output for performance bottlenecks and memory leaks'"
              className="w-full p-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={consultHiringManager}
              disabled={hiringLoading}
              className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
            >
              {hiringLoading ? 'Consulting Hiring Manager...' : 'Consult Hiring Manager'}
            </button>
          </div>

          {recommendation && (
            <div className="p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
              <div className="font-medium text-purple-800 dark:text-purple-300 mb-1">
                Hiring Manager Recommendation
              </div>
              <div className="text-sm text-purple-700 dark:text-purple-400 space-y-1">
                <div>Position: <strong>{recommendation.recommended_position}</strong></div>
                <div>Placement: {recommendation.placement}</div>
                <div>Confidence: {recommendation.confidence}</div>
                <div className="text-xs opacity-80">{recommendation.rationale}</div>
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Position (Pipeline Order)
            </label>
            <input
              type="number"
              value={newPosition}
              onChange={(e) => setNewPosition(e.target.value)}
              placeholder={recommendation ? String(recommendation.recommended_position) : '99'}
              className="w-full p-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
            <p className="text-xs text-gray-500 mt-1">
              Lower numbers run earlier in the pipeline. Use the Hiring Manager to get a recommendation.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              System Prompt (Optional)
            </label>
            <textarea
              value={newSystemPrompt}
              onChange={(e) => setNewSystemPrompt(e.target.value)}
              rows={6}
              placeholder="Custom system prompt for this agent. If left blank, the agent will use a generic prompt."
              className="w-full p-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:outline-none font-mono text-sm"
            />
          </div>

          <div className="pt-2">
            <button
              onClick={createAgent}
              disabled={saving}
              className="px-6 py-2.5 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {saving ? 'Adding...' : 'Add Agent to Pipeline'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
