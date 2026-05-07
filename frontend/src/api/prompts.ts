import api from './client'
import type { PromptTemplate, ChatMessage, PromptFields, AgentPreview } from '../types'

export const promptsApi = {
  listTemplates: () =>
    api.get<PromptTemplate[]>('/prompts/templates').then(r => r.data),

  getTemplate: (id: string) =>
    api.get<PromptTemplate>(`/prompts/templates/${id}`).then(r => r.data),

  createTemplate: (payload: Partial<PromptTemplate>) =>
    api.post<PromptTemplate>('/prompts/templates', payload).then(r => r.data),

  updateTemplate: (id: string, payload: Partial<PromptTemplate>) =>
    api.patch<PromptTemplate>(`/prompts/templates/${id}`, payload).then(r => r.data),

  deleteTemplate: (id: string) =>
    api.delete(`/prompts/templates/${id}`),

  chat: (messages: ChatMessage[], currentFields: PromptFields | null, templateId?: string) =>
    api.post<{ reply: string; updated_fields: PromptFields; generated_prompt: string | null }>('/prompts/chat', {
      messages,
      current_fields: currentFields,
      template_id: templateId,
    }).then(r => r.data),

  generate: (fields: PromptFields, contextSummary?: string) =>
    api.post<{ final_prompt: string; agent_previews: Record<string, AgentPreview> }>('/prompts/generate', {
      fields,
      context_summary: contextSummary,
    }).then(r => r.data),
}
