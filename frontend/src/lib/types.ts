// Types that mirror backend Pydantic schemas. Keep in sync manually.

export interface UserProfile {
  user_id: string
  email: string
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegisterResponse {
  user_id: string
  email: string
  access_token: string
  token_type: string
}

export interface CreateSessionResponse {
  session_id: string
  status: string
  created_at: string
}

export interface SessionListItem {
  session_id: string
  goal: string
  status: string
  final_quality: number | null
  created_at: string
}

export interface SessionList {
  items: SessionListItem[]
  total: number
  limit: number
  offset: number
}

export interface Citation {
  url: string
  title: string
  snippet: string
}

export interface SessionDetail {
  session_id: string
  goal: string
  status: string
  iteration_count: number
  final_quality: number | null
  final_output: Record<string, unknown> | null
  citations: Citation[]
  created_at: string
  completed_at: string | null
}

// WebSocket frame union ---------------------------------------------------

export interface ConnectedFrame   { type: 'connected';      session_id: string }
export interface AgentStartFrame  { type: 'agent_start';    agent: string; iteration: number; ts: string }
export interface AgentCompleteFrame { type: 'agent_complete'; agent: string; output_preview: string; ts: string }
export interface AgentProgressFrame { type: 'agent_progress'; agent: string; message: string; ts: string }
export interface QualityScoreFrame { type: 'quality_score'; score: number; iteration: number; breakdown: Record<string, number> }
export interface ReplanFrame      { type: 'replan';         iteration: number; feedback: string }
export interface ErrorFrame       { type: 'error';          code: string; message: string; agent: string | null }
export interface DoneFrame        { type: 'done';           output: Record<string, string>; citations: Citation[]; final_score: number; disclaimer: string | null }
export interface PongFrame        { type: 'pong' }

export type StreamFrame =
  | ConnectedFrame
  | AgentStartFrame
  | AgentCompleteFrame
  | AgentProgressFrame
  | QualityScoreFrame
  | ReplanFrame
  | ErrorFrame
  | DoneFrame
  | PongFrame
