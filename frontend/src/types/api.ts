// A job's status as the API reports it.
export type ServerJobStatus =
  | 'waiting'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'upstream_failed'
  | 'cancelled';

// A job's status as the UI shows it ('Draft': not submitted yet).
export type JobStatus =
  | 'Draft'
  | 'Pending'
  | 'Running'
  | 'Success'
  | 'Failed'
  | 'Blocked'
  | 'Ready'
  | 'Cancelled';

export type SaveStatus = 'saved' | 'saving' | 'deployed' | 'idle';

export interface QuotaResponse {
  runsRemaining: number;
}

// Task catalog (GET /api/task-definitions); mirrors app/catalog/models.py.
export type ParameterKind = 'boolean' | 'integer' | 'number' | 'string';

export type ParameterValue =
  | boolean
  | number
  | string
  | null
  | Array<boolean | number | string>;

export interface ParameterSpec {
  name: string;
  flag: string;
  kind: ParameterKind;
  default: ParameterValue;
  choices: Array<boolean | number | string> | null;
  multiple: boolean;
  required: boolean;
  help: string | null;
  label: string | null;
  unit: string | null;
  minimum: number | null;
  maximum: number | null;
}

export interface InputPort {
  name: string;
  flag: string;
  formats: string[];
  required: boolean;
  multiple: boolean;
}

export interface OutputPort {
  name: string;
  glob: string;
}

export interface TaskDefinition {
  id: string;
  title: string;
  description: string;
  category: string;
  module: string;
  resources: {
    cpus: number;
    memory_mb: number;
    walltime_minutes: number;
    // MPI processes rather than threads (Quantum ESPRESSO).
    mpi?: boolean;
  };
  platform_flags: { job_name: string | null; cpus: string | null };
  inputs: InputPort[];
  outputs: OutputPort[];
  parameters: ParameterSpec[];
  // Data packs the agent puts in place first (pseudopotentials...).
  data?: DataNeed[];
}

// A data pack a task reads, and the variable that names its folder.
export interface DataNeed {
  name: string;
  version: string;
  env: string;
}

// Input port name -> uploaded file names.
export type InputFiles = Record<string, string[]>;

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
  // The handles the edge is attached to; drafts saved before these
  // existed get the usual ones on load.
  source_handle?: string | null;
  target_handle?: string | null;
}

export interface PipelineBlueprint {
  nodes: BlueprintNode[];
  edges: BlueprintEdge[];
}

export interface PipelineSubmitNode {
  ui_id: string;
  script_name: string;
  parameters: Record<string, any>;
  inputs: InputFiles;
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
  // Where to run; the shared AtomField server if absent.
  target_id?: string | null;
}

export interface PipelineSubmitResponse {
  job_ids: Record<string, string>;
  pipeline_id: string;
  run_id: string;
  total_nodes: number;
  roots_started: number;
}

export interface JobLogsResponse {
  status: ServerJobStatus;
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
  run_id: string;
  script_name: string;
  status: ServerJobStatus;
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

// One job's new state, numbered within its run (live stream "job").
export interface JobEvent {
  run_id: string;
  seq: number;
  job_id: string;
  status: ServerJobStatus;
  attempt: number;
  error_message?: string | null;
  // False while a "running" job still waits in a cluster's queue.
  started?: boolean;
}

// One job's state inside a snapshot.
export interface JobState {
  job_id: string;
  status: ServerJobStatus;
  attempt: number;
  error_message?: string | null;
  started?: boolean;
}

// Every job of a run plus the run's counter (live stream "snapshot").
export interface RunSnapshot {
  run_id: string;
  seq: number;
  jobs: JobState[];
}

// Where a run's files stayed (a cluster or laptop), with a command
// ready to copy them when the machine can be reached by rsync.
export interface FolderInfo {
  path: string;
  address?: string | null;
  copy_command?: string | null;
}

// How to get a run's files: a zip download, or where they are.
export interface BundleInfo {
  run_id: string;
  finished: boolean;
  status:
    | 'none'
    | 'requested'
    | 'packing'
    | 'ready'
    | 'too_big'
    | 'failed'
    | 'expired';
  size_bytes?: number | null;
  expires_at?: string | null;
  download_url?: string | null;
  error?: string | null;
  folder?: FolderInfo | null;
  // The scripts release the run used, e.g. "afscripts 0.2.0+g2e6d386",
  // and the data packs its tasks read.
  made_with?: string | null;
  data_packs?: string[];
}

// A place runs can execute: the shared AtomField server, or one of the
// user's own clusters or computers.
export interface ComputeTarget {
  id: string;
  name: string;
  kind: string;
  shared: boolean;
  last_seen_at?: string | null;
  online: boolean;
}

// A target with its agent token, returned once when created.
export interface TargetToken {
  target: ComputeTarget;
  token: string;
}
