export type BuildStatus = 'created' | 'queued' | 'running' | 'failed' | 'completed'
export type BuildPhase = 'architecting' | 'coding' | 'designing' | 'hardening' | 'validating' | 'building' | 'testing'
export type BuildMode = 'fast' | 'quality'

export interface Build {
  id: string
  project_name: string
  requirement: string
  stack_target: string
  mode: BuildMode
  status: BuildStatus
  current_phase: BuildPhase | null
  retry_count: number
  error_message: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface BuildEvent {
  id: string
  build_id: string
  phase: string | null
  event_type: string
  message: string
  payload: string | null
  created_at: string
  timestamp?: string
}

export interface GeneratedFile {
  id: string
  build_id: string
  file_path: string
  file_name: string
  content_preview: string | null
  size_bytes: number
  phase: string
  created_at: string
}

export interface Finding {
  id: string
  build_id: string
  severity: 'low' | 'medium' | 'high'
  category: string
  file_path: string | null
  line_number: number | null
  description: string
  remediation: string | null
  created_at: string
}

export interface AppSettings {
  ollama_base_url: string
  ollama_fast_model: string
  ollama_quality_model: string
  ollama_timeout: number
  workspace_path: string
}

export interface WsEvent {
  build_id: string
  event_type: string
  message: string
  phase: string | null
  status: string | null
  payload: string | null
  timestamp: string
}

export interface PromptTemplate {
  id: string
  name: string
  description: string | null
  what_to_build: string | null
  target_audience: string | null
  platform_type: string | null
  key_features: string | null
  constraints: string | null
  tech_stack: string | null
  security_sensitivity: string | null
  output_format: string | null
  final_prompt: string | null
  conversation_history: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface PromptFields {
  what_to_build?: string
  target_audience?: string
  platform_type?: string
  key_features?: string
  constraints?: string
  tech_stack?: string
  security_sensitivity?: string
  output_format?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ProjectContext {
  id: string
  name: string
  source_dir: string | null
  workspace_dir: string | null
  output_dir: string | null
  detected_stack: string | null
  detected_files: string | null
  inferred_project_type: string | null
  context_summary: string | null
  context_summary_json: string | null
  total_files_scanned: number
  last_scanned_at: string | null
  created_at: string
  updated_at: string
}

export interface FileManifestEntry {
  id: string
  context_id: string
  relative_path: string
  file_name: string
  extension: string | null
  size_bytes: number
  is_key_file: boolean
  detected_language: string | null
  created_at: string
}

export interface ScanResult {
  context_id: string
  detected_stack: string[]
  inferred_project_type: string
  total_files: number
  key_files: string[]
  ignored_folders: string[]
  context_summary: string
  context_summary_json: Record<string, unknown>
}

export interface BuildDirectoryConfig {
  id: string
  build_id: string
  source_dir: string | null
  workspace_dir: string | null
  output_dir: string | null
  project_context_id: string | null
  prompt_template_id: string | null
  final_output_path: string | null
  files_written: number
  created_at: string
  updated_at: string
}

export interface AgentPreview {
  agent: string
  input_summary: string
  stack?: string
  prompt_preview?: string
  note?: string
  checks?: string[]
  retry_budget?: number
}
