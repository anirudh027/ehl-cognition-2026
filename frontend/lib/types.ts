export type AgentTrace = {
  id: string;
  source: string;
  body: string;
  created_at: string;
};

export type Agent = {
  id: string;
  parent_id: string | null;
  role: string;
  name: string;
  status: string;
  summary: string;
  external_id: string | null;
  url: string | null;
  acus_consumed: number;
  traces: AgentTrace[];
};

export type RunEvent = {
  id: number;
  agent_id: string | null;
  type: string;
  title: string;
  detail: string;
  tone: string;
  created_at: string;
};

export type Artifact = {
  id: string;
  kind: string;
  name: string;
  description: string;
  content_type: string;
  created_at: string;
};

export type Candidate = {
  id: string;
  version: number;
  mutation: string;
  position: number;
  score: number;
  distance: number;
  conservation: number;
  evidence: string[];
  rationale: string;
  excluded: boolean;
};

export type RunMessage = {
  id: string;
  body: string;
  created_at: string;
};

export type Run = {
  id: string;
  objective: string;
  mode: string;
  status: string;
  stage: string;
  progress: number;
  result_version: number;
  created_at: string;
  updated_at: string;
  agents: Agent[];
  events: RunEvent[];
  artifacts: Artifact[];
  candidates: Candidate[];
  messages: RunMessage[];
};
