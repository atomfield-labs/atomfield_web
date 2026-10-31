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

export type SaveStatus = 'saved' | 'saving' | 'deployed' | 'idle' | 'failed';

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

// Ready-made pipelines (GET /api/pipeline-templates), shipped in the
// scripts release beside the tasks they use.
export interface TemplateStructure {
  key: string;
  filename: string;
  content: string;
}

export interface TemplateStep {
  key: string;
  task: string;
  label: string;
  // Keys of the structures and earlier steps it reads from.
  after: string[];
  // Only the values that differ from the task's defaults.
  parameters: Record<string, ParameterValue>;
}

export interface PipelineTemplate {
  id: string;
  title: string;
  description: string;
  structures: TemplateStructure[];
  steps: TemplateStep[];
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

// How a pipeline stands, from its newest run.
export type SessionState =
  | 'draft'
  | 'waiting'
  | 'running'
  | 'done'
  | 'failed'
  | 'cancelled';

export interface SessionSummary {
  id: string;
  // None until the person or a template names it.
  title: string | null;
  state: SessionState;
  node_count: number;
  updated_at: string;
}

export interface SessionDetail extends SessionSummary {
  blueprint: PipelineBlueprint | null;
  run_id: string | null;
  // Which job each node of the newest run became.
  job_ids: Record<string, string>;
}

// What changed about a pipeline; what is left out stays.
export interface SessionSave {
  title?: string;
  blueprint?: PipelineBlueprint;
  node_count?: number;
}

// A person as the API shows them: who they are and their job quota.
// key_prefix is set only when a script's key made the request.
export interface AccountQuota {
  key_prefix?: string | null;
  label?: string | null;
  email?: string | null;
  quota_limit: number;
  quota_used: number;
  quota_remaining: number;
}

export type Role = 'owner' | 'admin' | 'user';

// A workflow, as a lab's page names it.
export interface WorkflowName {
  id: string;
  title: string;
}

// What a lab can be given: a named bundle of tasks and pipelines.
export interface Workflow extends WorkflowName {
  description: string;
  tasks: string[];
  pipelines: string[];
}

export interface LabSummary {
  id: string;
  name: string;
  workflows: WorkflowName[];
  people: number;
}

export interface LabPerson {
  id: string;
  email: string | null;
  name: string | null;
  role: Role;
  workflows: string[];
  last_seen_at: string | null;
}

export interface LabDetail {
  id: string;
  name: string;
  // What the lab has, and what the one asking could give it.
  workflows: WorkflowName[];
  available: WorkflowName[];
  people: LabPerson[];
}

export interface Account extends AccountQuota {
  is_active: boolean;
  role: Role;
  lab_id: string | null;
}

export interface UserStatsResponse extends AccountQuota {
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  pending_jobs: number;
}

// A computer asking to be paired, as its agent describes it.
export interface PairingView {
  code: string;
  hostname: string;
  username: string;
  address: string;
  kind: string;
  requested_at: string;
}

export interface AdminStatsResponse {
  total_users: number;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  total_compute_seconds: number;
}

export interface AdminUserSummary extends AccountQuota {
  id: string;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  total_compute_seconds: number;
  is_active: boolean;
  role: Role;
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
