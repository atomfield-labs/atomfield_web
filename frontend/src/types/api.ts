export type JobStatus = 'Draft' | 'Pending' | 'Running' | 'Success' | 'Failed' | 'Blocked' | 'Ready';

export type SaveStatus = 'saved' | 'saving' | 'deployed' | 'idle';

export interface QuotaResponse {
  runsRemaining: number;
}

export interface ScriptManifestItem {
  id: string;
  filename: string;
  title: string;
  description: string;
  default_parameters: Record<string, any>;
}

export interface BlueprintNode {
  ui_id: string;
  id: string;
  type: 'structure' | 'default' | 'branchCircle' | string;
  label?: string;
  script_name?: string;
  filename?: string;
  status?: string;
  parameters?: Record<string, any>;
  default_parameters?: Record<string, any>;
  position?: { x: number; y: number };
  node_type?: string;
  workspace_path?: string;
  atom_count?: number;
  formula?: string;
  elements?: Record<string, number>;
  atoms?: any[];
  comment?: string;
  bounding_box?: any;
  raw_content?: string;
  originalData?: any;
  [key: string]: any;
}

export interface BlueprintEdge {
  id?: string;
  upstream_ui_id: string;
  downstream_ui_id: string;
}

export interface PipelineBlueprint {
  nodes: BlueprintNode[];
  edges: BlueprintEdge[];
}

export interface PipelineSubmitNode {
  ui_id: string;
  script_name: string;
  parameters: Record<string, any>;
}

export interface PipelineSubmitEdge {
  upstream_ui_id: string;
  downstream_ui_id: string;
}

export interface PipelineSubmitFile {
  filename: string;
  content: string;
}

export interface PipelineSubmitRequest {
  session_id: string;
  nodes: PipelineSubmitNode[];
  edges: PipelineSubmitEdge[];
  files: PipelineSubmitFile[];
}

export interface PipelineSubmitResponse {
  job_ids: Record<string, string>;
  pipeline_id: string;
  total_nodes: number;
  roots_started: number;
}

export interface JobLogsResponse {
  status: JobStatus;
  logs: string;
  artifacts: string[];
}

export interface SessionMetadata {
  id: string;
  title: string;
  status: JobStatus;
  nodeCount: number;
  updatedAt: string;
}

export interface JobItem {
  id: string;
  script_name: string;
  status: JobStatus;
  parameters: Record<string, any>;
  output_data?: Record<string, any> | null;
  error_message?: string | null;
  execution_time_seconds?: number | null;
  created_at: string;
}

export interface JobListResponse {
  jobs: JobItem[];
  total: number;
}

export interface ApiKeyCreateRequest {
  label?: string;
}

export interface ApiKeyCreateResponse {
  api_key: string;
  key_prefix: string;
  label?: string | null;
  quota_limit: number;
  quota_used: number;
}

export interface ApiKeyInfo {
  key_prefix: string;
  label?: string | null;
  quota_limit: number;
  quota_used: number;
  quota_remaining: number;
  is_active: boolean;
  is_admin?: boolean;
}

export interface UserStatsResponse {
  key_prefix: string;
  label?: string | null;
  quota_limit: number;
  quota_used: number;
  quota_remaining: number;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  pending_jobs: number;
}

export interface AdminStatsResponse {
  total_users: number;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  total_compute_seconds: number;
}

export interface AdminUserSummary {
  id: string;
  key_prefix: string;
  label?: string | null;
  quota_limit: number;
  quota_used: number;
  quota_remaining: number;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  total_compute_seconds: number;
  is_active: boolean;
  created_at?: string | null;
  last_used_at?: string | null;
}

export interface AdminUserListResponse {
  users: AdminUserSummary[];
  total: number;
}

export interface AdminQuotaUpdateRequest {
  quota_limit?: number;
  reset_quota_used?: boolean;
}
