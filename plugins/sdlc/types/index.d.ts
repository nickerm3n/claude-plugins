export type StepView = { step: 'code' | 'judge' | 'human'; status: string; detail: string }

export type PhaseView = { name: string; status: string; steps: StepView[] }

export type RunView = {
  key: string
  title: string
  status: string
  pipeline: string
  current: string
  position: number
  total: number
  passed: number
  phases: PhaseView[]
  retries: number
  planStep: number | null
  pr: string | null
  waitReason: string
  last: string
  updatedAt: string
  lastRewind: { from: string; to: string } | null
}

export type Move = { key: string; from: string; to: string; kind: 'advance' | 'retry' | 'rewind'; at: number }

export type AgentActivity = {
  id: string
  type: string
  status: string
  firstSeen: number
  tools: number
  recent: string[]
}

export type Spend = { usd: number | null; contextPercent: number | null }

declare module 'claude-code' {
  interface PluginState {
    sdlc: {
      runs: Shaped<RunView[]>
      agents: Shaped<AgentActivity[]>
      spend: Shaped<Spend>
      move: Shaped<Move | null>
      view: string
      frame: number
    }
  }
}
