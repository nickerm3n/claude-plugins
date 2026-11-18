import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AgentActivity, Move, PhaseView, RunView, Spend, StepView } from '../types'

const PANE = 'sdlc-runs'
const TITLE = 'AI SDLC'
const RUNS_DIR = '.sdlc/runs'
const POLL_MS = 2000
const FRAME_MS = 400
// Change a tag when its type changes: it declines what an earlier version stored.
const runs = atom({ plugin: 'sdlc', key: 'runs' } as const, [], { shape: 'runs-3' })
const agents = atom({ plugin: 'sdlc', key: 'agents' } as const, [], { shape: 'agents-1' })
const spend = atom({ plugin: 'sdlc', key: 'spend' } as const, { usd: null, contextPercent: null }, { shape: 'spend-1' })
const move = atom({ plugin: 'sdlc', key: 'move' } as const, null, { shape: 'move-1' })
const view = atom({ plugin: 'sdlc', key: 'view' } as const, 'graph')
const frame = atom({ plugin: 'sdlc', key: 'frame' } as const, 0)
const MOVE_MS = 6000

type Tone = 'success' | 'warning' | 'error' | 'suggestion' | 'inactive' | 'claude'

const LABEL: Record<string, string> = {
  task: 'Task',
  enrich: 'Enrich',
  research: 'Research',
  design: 'Design',
  'qa-plan': 'QA Plan',
  plan: 'Plan',
  code: 'Code',
  'qa-check': 'QA Check',
  deploy: 'Deploy',
  qa: 'QA',
}
const FLOW: Record<string, [string, string, string]> = {
  task: ['Jira', 'jira.py', '01-task'],
  enrich: ['01-task', 'you ⇄ agent', '02-enrich'],
  research: ['task+enrich+code', 'researcher', '03-research'],
  design: ['03-research', 'designer', '04-design'],
  'qa-plan': ['04-design', 'qa-planner', '05-qa-plan'],
  plan: ['design+qa-plan', 'planner', '06-plan'],
  code: ['06-plan step', 'coder', 'commit'],
  'qa-check': ['qa-plan+diff', 'qa-checker', '08-qa-check'],
  deploy: ['merged PR', 'CI', 'dev'],
  qa: ['dev', 'e2e', '10-qa'],
}
const AGENT_PHASE: Record<string, string> = {
  researcher: 'research',
  designer: 'design',
  'qa-planner': 'qa-plan',
  planner: 'plan',
  coder: 'code',
  'qa-checker': 'qa-check',
  'judge-artifact': 'judge',
  'judge-architecture': 'judge',
}
const STEP_LABEL: Record<StepView['step'], string> = { code: 'code', judge: 'judge', human: 'you' }
const PHASE_MARK: Record<string, [string, Tone]> = {
  pending: ['○', 'inactive'],
  running: ['◉', 'claude'],
  retry: ['↻', 'warning'],
  waiting: ['◐', 'warning'],
  passed: ['●', 'success'],
  skipped: ['◌', 'inactive'],
  escalated: ['✖', 'error'],
}
const STEP_MARK: Record<string, [string, Tone, string]> = {
  pending: ['·', 'inactive', 'not yet'],
  pass: ['✓', 'success', 'passed'],
  fail: ['✗', 'error', 'failed'],
  PASS: ['✓', 'success', 'passed'],
  FAIL: ['✗', 'error', 'sent back'],
  DESIGN_ISSUE: ['◆', 'error', 'design issue'],
  waiting: ['⏸', 'warning', 'waiting for you'],
  approved: ['✓', 'success', 'approved'],
}
const RUN_TONE: Record<string, Tone> = { running: 'claude', waiting_human: 'warning', escalated: 'error', done: 'success' }
const RUN_TEXT: Record<string, string> = { running: 'running', waiting_human: 'waiting for you', escalated: 'escalated', done: 'done' }
const SPIN = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
const PULSE = ['◉', '◎', '○', '◎']
const FLOW_DOTS = ['•  ', ' • ', '  •']

type RunJson = {
  key: string
  status: string
  pipeline: string
  current: string
  phases: string[]
  phase_status: Record<string, string>
  retries: Record<string, number>
  plan_step: number | null
  pr: string | null
  updated_at?: string
  gate_plan?: Record<string, StepView['step'][]>
  gates?: Record<string, Record<string, { status: string; detail?: string }>>
  history?: { phase: string; event: string; detail?: string }[]
}

function firstLine(text: string | undefined): string {
  return (text ?? '').split('\n')[0] ?? ''
}

function clip(text: string, width: number): string {
  return text.length > width ? text.slice(0, Math.max(1, width - 1)) + '…' : text
}

function shortPath(path: string): string {
  const parts = path.split('/')
  return parts.length > 3 ? '…/' + parts.slice(-2).join('/') : path
}

function elapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
}

export function toView(run: RunJson, title: string): RunView {
  const history = run.history ?? []
  const last = history.at(-1)
  const wait = [...history].reverse().find(e => e.event === 'wait' || e.event === 'escalate' || e.event === 'fail')
  let lastRewind: RunView['lastRewind'] = null
  history.forEach((e, i) => {
    if (e.event === 'rewind') lastRewind = { from: history[i - 1]?.phase ?? e.phase, to: e.phase }
  })
  const phases: PhaseView[] = run.phases.map(name => {
    const plan = run.gate_plan?.[name] ?? ['code']
    const gates = run.gates?.[name] ?? {}
    return {
      name,
      status: run.phase_status[name] ?? 'pending',
      steps: plan.map(step => ({ step, status: gates[step]?.status ?? 'pending', detail: gates[step]?.detail ?? '' })),
    }
  })
  return {
    key: run.key,
    title,
    status: run.status,
    pipeline: run.pipeline,
    current: run.current,
    position: run.phases.indexOf(run.current) + 1,
    total: run.phases.length,
    passed: phases.filter(p => p.status === 'passed' || p.status === 'skipped').length,
    phases,
    retries: run.retries[run.current] ?? 0,
    planStep: run.plan_step,
    pr: run.pr,
    waitReason: run.status === 'running' ? '' : firstLine(wait?.detail),
    last: last ? `${LABEL[last.phase] ?? last.phase} ${last.event}${last.detail ? ': ' + firstLine(last.detail) : ''}` : '',
    updatedAt: run.updated_at ?? '',
    lastRewind,
  }
}

export type Seg = { t: string; c?: Tone; b?: boolean; d?: boolean }

export function detectMove(prev: RunView | undefined, next: RunView, at: number): Move | null {
  if (!prev || prev.key !== next.key) return null
  if (prev.current !== next.current) {
    const names = next.phases.map(p => p.name)
    const kind = names.indexOf(next.current) > names.indexOf(prev.current) ? 'advance' : 'rewind'
    return { key: next.key, from: prev.current, to: next.current, kind, at }
  }
  if (next.retries > prev.retries) return { key: next.key, from: next.current, to: next.current, kind: 'retry', at }
  return null
}

export function moveCaption(m: Move): string {
  const from = LABEL[m.from] ?? m.from
  const to = LABEL[m.to] ?? m.to
  if (m.kind === 'advance') return `${from} ✓ ▸ ${to}`
  if (m.kind === 'rewind') return `${from} ⟲ back to ${to}`
  return `${to} sent back ↺`
}

// The state machine as a minimal graph: one node per phase, edges between them,
// arcs underneath for the paths that go backwards, and a pointer at the current node.
export function graphRows(v: RunView, width: number, tick: number, hot: Move | null, tone: Tone): Seg[][] {
  const n = v.phases.length
  const step = width >= 3 * n - 2 ? 3 : 2
  const edge = step - 1
  const col = (i: number) => step * i
  const idx = (name: string) => v.phases.findIndex(p => p.name === name)
  const cur = idx(v.current)
  const live = v.status === 'running'
  const from = hot?.kind === 'advance' ? idx(hot.from) : -1
  const to = hot?.kind === 'advance' ? idx(hot.to) : -1

  const nodes: Seg[] = []
  v.phases.forEach((p, i) => {
    const [mark, ptone] = PHASE_MARK[p.status] ?? ['?', 'inactive']
    const here = i === cur && v.status !== 'done'
    nodes.push({ t: here && live ? PULSE[tick % PULSE.length] : mark, c: here ? tone : ptone, b: here })
    if (i === n - 1) return
    if (from >= 0 && i >= from && i < to) {
      nodes.push({ t: tick % 2 === 0 ? '━'.repeat(edge - 1) + '▸' : '━'.repeat(edge), c: 'claude', b: true })
    } else if (p.status === 'passed' || p.status === 'skipped') {
      nodes.push({ t: '━'.repeat(edge), c: 'success' })
    } else if (here && live) {
      nodes.push({ t: tick % 2 === 0 ? '┈'.repeat(edge - 1) + '›' : '›' + '┈'.repeat(edge - 1), c: tone })
    } else {
      nodes.push({ t: '┈'.repeat(edge), c: 'inactive' })
    }
  })
  const rows: Seg[][] = [nodes]

  type Arc = { from: number; to: number; label: string; c: Tone; hot: boolean }
  const arcs: Arc[] = []
  const design = idx('design')
  if (v.phases[cur]?.steps.some(s => s.status === 'DESIGN_ISSUE') && design >= 0 && design < cur) {
    arcs.push({ from: cur, to: design, label: 'design issue', c: 'error', hot: true })
  }
  if (v.lastRewind) {
    const f = idx(v.lastRewind.from)
    const t = idx(v.lastRewind.to)
    if (t >= 0 && f > t && cur <= f && !arcs.some(a => a.from === f && a.to === t)) {
      arcs.push({ from: f, to: t, label: 'rewind', c: 'warning', hot: hot?.kind === 'rewind' })
    }
  }
  for (const a of arcs) {
    const inner = col(a.from) - col(a.to) - 1
    const tail = col(a.from) + 2 + a.label.length <= width ? ` ${a.label}` : ''
    rows.push([
      { t: ' '.repeat(col(a.to)) },
      { t: `▴${'─'.repeat(inner)}╯${tail}`, c: a.c, b: a.hot, d: !a.hot },
    ])
  }

  if (cur >= 0) {
    const retry = hot?.kind === 'retry'
    const label = `${LABEL[v.current] ?? v.current} · ${RUN_TEXT[v.status] ?? v.status}${v.retries > 0 ? ` ↺${v.retries}` : ''}`
    const at = col(cur)
    const c: Tone = retry ? 'warning' : tone
    rows.push(
      at + 2 + label.length <= width
        ? [{ t: `${' '.repeat(at)}▲ `, c, b: true }, { t: label, c }]
        : [{ t: `${label.padStart(Math.max(0, at - 1))} ▲`, c, b: true }],
    )
  }
  return rows
}

export function summary(v: RunView): string {
  const step = v.current === 'code' && v.planStep ? ` step ${v.planStep}` : ''
  const retry = v.retries > 0 ? ` ↻${v.retries}` : ''
  const state = v.status === 'running' ? '' : ` · ${RUN_TEXT[v.status] ?? v.status}`
  return `${v.key} ▸ ${LABEL[v.current] ?? v.current} ${v.position}/${v.total}${step}${retry}${state}`
}

function bar(v: RunView, width: number, tick: number): [string, string, string] {
  const done = Math.round((v.passed / Math.max(1, v.total)) * width)
  const head = v.status === 'done' || done >= width ? '' : tick % 2 === 0 ? '╸' : '━'
  return ['━'.repeat(done), head, '─'.repeat(Math.max(0, width - done - head.length))]
}

async function refresh($: EngineInterface): Promise<RunView[]> {
  if (!(await $.fs.exists(RUNS_DIR))) return []
  const views: RunView[] = []
  for (const entry of await $.fs.list(RUNS_DIR)) {
    if (entry.kind !== 'dir') continue
    const text = await $.fs.read(`${RUNS_DIR}/${entry.name}/run.json`).catch(() => undefined)
    if (typeof text !== 'string') continue
    const task = await $.fs.read(`${RUNS_DIR}/${entry.name}/01-task.md`).catch(() => undefined)
    const title = typeof task === 'string' ? firstLine(task).replace(/^#\s*[A-Z][A-Z0-9]+-\d+\s*·\s*/, '') : ''
    try {
      views.push(toView(JSON.parse(text) as RunJson, title))
    } catch {
      continue
    }
  }
  views.sort((a, b) => Number(a.status === 'done') - Number(b.status === 'done') || b.updatedAt.localeCompare(a.updatedAt))
  const before = await read($, runs)
  const top = views[0]
  if (top) {
    const m = detectMove(
      before.find(b => b.key === top.key),
      top,
      await $.clock.now(),
    )
    if (m) await update($, move, () => m)
  }
  if (JSON.stringify(before) !== JSON.stringify(views)) await update($, runs, () => views)
  const live = views.find(v => v.status !== 'done')
  $.ui.status(live ? summary(live) : undefined)
  return views
}

async function refreshAgents($: EngineInterface): Promise<void> {
  const listed = await $.agent.list().catch(() => [])
  const now = await $.clock.now()
  await update($, agents, current => {
    const byId = new Map(current.map(a => [a.id, a]))
    for (const a of listed) {
      const type = a.type.split(':').pop() ?? a.type
      if (!(type in AGENT_PHASE)) continue
      const known = byId.get(a.id)
      byId.set(a.id, { ...(known ?? { id: a.id, firstSeen: now, tools: 0, recent: [] }), type, status: a.status })
    }
    return [...byId.values()].filter(a => a.status === 'running' || a.status === 'pending' || now - a.firstSeen < 10 * 60_000).slice(-6)
  })
  const usage = await $.session.usage().catch(() => undefined)
  if (usage) {
    const next: Spend = { usd: usage.cost?.usd ?? null, contextPercent: usage.context.percent ?? null }
    const before = await read($, spend)
    if (before.usd !== next.usd || before.contextPercent !== next.contextPercent) await update($, spend, () => next)
  }
}

export function describeBash(command: string): string {
  const line = (command.split('\n')[0] ?? '').trim()
  const search = line.match(/^(?:rg|grep|git grep)\s+(?:-\S+\s+)*(?:"([^"]+)"|'([^']+)'|(\S+))/)
  if (search) return `search "${search[1] ?? search[2] ?? search[3]}"`
  return `$ ${line}`
}

async function track($: EngineInterface, agentId: string | undefined, what: string): Promise<void> {
  if (!agentId) return
  const now = await $.clock.now()
  await update($, agents, current => {
    const known = current.find(a => a.id === agentId)
    const base: AgentActivity = known ?? { id: agentId, type: '', status: 'running', firstSeen: now, tools: 0, recent: [] }
    const next = { ...base, tools: base.tools + 1, recent: [what, ...base.recent].slice(0, 3) }
    return known ? current.map(a => (a.id === agentId ? next : a)) : [...current, next].slice(-6)
  })
}

async function runCommand($: EngineInterface, command: string, args: string): Promise<void> {
  const ran = await $.command.run({ command, args }).catch(() => undefined)
  if (!ran) $.ui.toast(`Type /${command} ${args}`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await $.command.register({ name: 'sdlc-pane', description: 'Show the AI SDLC run as a live gate state machine beside the chat' })
    const views = await refresh($)
    await refreshAgents($)
    $.clock.every(POLL_MS, async () => {
      await refresh($)
      await refreshAgents($)
    })
    $.clock.every(FRAME_MS, async () => {
      const moved = await read($, move)
      const fresh = moved !== null && (await $.clock.now()) - moved.at < MOVE_MS
      const live = (await read($, runs)).some(v => v.status === 'running')
      if (live || fresh) await update($, frame, n => (n + 1) % 1000)
    })
    if (views.some(v => v.status !== 'done')) void $.ui.open({ id: PANE, title: TITLE })
    return started
  })

  on('command.run', { command: 'sdlc-pane' }, async $ => {
    await refresh($)
    await $.ui.open({ id: PANE, title: TITLE })
    return { text: 'AI SDLC pane opened.' }
  })

  on('tool.call', { tool: 'Read' }, async ($, e, next) => {
    void track($, e.agentId, `read ${shortPath(e.file_path)}`).catch(() => undefined)
    return next(e)
  })
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    void track($, e.agentId, `edit ${shortPath(e.file_path)}`).catch(() => undefined)
    return next(e)
  })
  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    void track($, e.agentId, `write ${shortPath(e.file_path)}`).catch(() => undefined)
    return next(e)
  })
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    void track($, e.agentId, describeBash(e.command)).catch(() => undefined)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const list = await read($, runs)
    const active = await read($, agents)
    const money = await read($, spend)
    const tick = await read($, frame)
    const mode = await read($, view)
    const moved = await read($, move)
    const now = await $.clock.now()
    const width = Math.max(28, (e.props.bodyColumns ?? 44) - 2)
    const v = list[0]
    const seg = (s: Seg) => (
      <Text color={s.c} bold={s.b} dimColor={s.d}>
        {s.t}
      </Text>
    )

    const spendLine = (
      <Text>
        <Text dimColor>spent </Text>
        <Text bold color="claude">{money.usd === null ? '—' : `$${money.usd.toFixed(2)}`}</Text>
        <Text dimColor>{money.contextPercent === null ? '' : `  ·  context ${Math.round(money.contextPercent)}%`}</Text>
      </Text>
    )

    if (!v) {
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold color="claude">◆ AI SDLC</Text>
          <Text bold>No pipeline runs yet</Text>
          <Text dimColor>Start one with /sdlc:feature PROJ-123.</Text>
          <Text dimColor>Each phase passes a gate: code checks → judge → you.</Text>
          {spendLine}
        </Box>
      )
    }

    const cur = v.phases.find(p => p.name === v.current)
    const hot = moved !== null && moved.key === v.key && now - moved.at < MOVE_MS ? moved : null
    const lastMove = moved !== null && moved.key === v.key ? moved : null
    const curLabel = LABEL[v.current] ?? v.current
    const tone = RUN_TONE[v.status] ?? 'inactive'
    const isLive = v.status === 'running'
    const spin = isLive ? SPIN[tick % SPIN.length] : v.status === 'done' ? '✓' : v.status === 'escalated' ? '✖' : '⏸'
    const [barDone, barHead, barRest] = bar(v, Math.min(24, width - 10), tick)
    const flow = FLOW[v.current] ?? ['', '', '']
    const worker = [...active].reverse().find(a => a.status === 'running' && AGENT_PHASE[a.type] !== undefined)
    const activeStep = cur?.steps.find(s => s.status === 'pending' || s.status === 'waiting' || s.status === 'fail' || s.status === 'FAIL')

    const callout = (() => {
      type Action = { key: string; label: string; primary?: boolean; run: () => Promise<void> }
      const none: Action[] = []
      if (v.status === 'done') return { head: 'All gates passed', body: v.pr ?? 'The run is complete.', actions: none, hint: '' }
      if (v.status === 'escalated') {
        return {
          head: `${curLabel} needs your decision`,
          body: v.waitReason || 'The gate failed more times than allowed.',
          actions: [{ key: 'continue', label: 'Retry phase', primary: true, run: () => runCommand($, 'sdlc:approve', v.current) }],
          hint: 'or /sdlc:rewind <phase> <why>',
        }
      }
      if (v.status === 'waiting_human') {
        if (v.current === 'design') {
          return {
            head: 'Review the design',
            body: `.sdlc/runs/${v.key}/04-design.md`,
            actions: [{ key: 'approve-design', label: 'Approve design', primary: true, run: () => runCommand($, 'sdlc:approve', 'design') }],
            hint: 'Not right? Tell the agent what to change.',
          }
        }
        if (v.current === 'deploy') {
          return {
            head: 'Merge to deploy',
            body: v.pr ?? 'Merge the pull request; CI deploys it.',
            actions: [{ key: 'resume', label: 'I merged it', primary: true, run: () => runCommand($, 'sdlc:feature', v.key) }],
            hint: '',
          }
        }
        if (v.current === 'code') {
          return {
            head: 'Judge found a design issue',
            body: v.waitReason,
            actions: [{ key: 'fix-code', label: 'Fix code only', primary: true, run: () => runCommand($, 'sdlc:approve', 'code') }],
            hint: 'or /sdlc:rewind design <why>',
          }
        }
        return { head: `${curLabel}: your turn`, body: v.waitReason || 'The agent is waiting for your answer in the chat.', actions: none, hint: '' }
      }
      return { head: '', body: '', actions: [{ key: 'resume', label: 'Resume', run: () => runCommand($, 'sdlc:feature', v.key) }], hint: '' }
    })()

    const gateChain = (cur?.steps ?? []).map((s, i) => {
      const [mark, stone] = STEP_MARK[s.status] ?? ['?', 'inactive']
      const isActive = s === activeStep
      const glyph = isActive && isLive && s.status === 'pending' ? SPIN[tick % SPIN.length] : mark
      return (
        <Text>
          {i > 0 && <Text dimColor>{isActive && isLive ? ` ${FLOW_DOTS[tick % FLOW_DOTS.length]}▸ ` : ' ──▸ '}</Text>}
          <Text color={isActive ? tone : stone} bold={isActive}>{`${glyph} ${STEP_LABEL[s.step]}`}</Text>
        </Text>
      )
    })

    const phaseRow = (p: PhaseView, i: number) => {
      const [mark, ptone] = PHASE_MARK[p.status] ?? ['?', 'inactive']
      const isCur = p.name === v.current && v.status !== 'done'
      const glyph = isCur && isLive ? PULSE[tick % PULSE.length] : mark
      const prev = v.phases[i - 1]
      const linkDone = prev?.status === 'passed' || prev?.status === 'skipped'
      const linkLive = isCur && isLive
      const chips = p.steps.map(s => (STEP_MARK[s.status] ?? ['?'])[0]).join(' ')
      return (
        <Box flexDirection="column">
          {i > 0 && (
            <Text color={linkDone ? 'success' : linkLive ? tone : 'inactive'}>
              {linkDone ? '  ┃' : linkLive ? (tick % 2 === 0 ? '  ╏' : '  ┇') : '  ┊'}
            </Text>
          )}
          <Text>
            <Text color={isCur ? tone : ptone} bold={isCur}>{`  ${glyph} `}</Text>
            <Text bold={isCur} color={isCur ? tone : undefined} dimColor={!isCur && (p.status === 'pending' || p.status === 'skipped')}>
              {(LABEL[p.name] ?? p.name).padEnd(10)}
            </Text>
            {isCur ? <Text color={tone}>{`◀ ${RUN_TEXT[v.status] ?? v.status}`}</Text> : <Text dimColor>{chips}</Text>}
          </Text>
        </Box>
      )
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text>
            <Text bold color="claude">◆ AI SDLC  </Text>
            <Text bold>{v.key}</Text>
            <Text dimColor>{` · ${v.pipeline}`}</Text>
          </Text>
          {v.title !== '' && <Text dimColor>{clip(v.title, width)}</Text>}
          <Text>
            <Text color="success">{barDone}</Text>
            <Text color={tone}>{barHead}</Text>
            <Text dimColor>{barRest}</Text>
            <Text bold>{`  ${v.passed}/${v.total}`}</Text>
          </Text>
          {spendLine}
        </Box>

        <Box flexDirection="column" borderStyle="round" borderColor={tone} paddingX={1}>
          <Text>
            <Text color={tone} bold>{`${spin} ${curLabel}`}</Text>
            <Text dimColor>{` · ${RUN_TEXT[v.status] ?? v.status}`}</Text>
            {v.current === 'code' && v.planStep !== null && <Text dimColor>{` · plan step ${v.planStep}`}</Text>}
            {v.retries > 0 && <Text color="warning">{` · retry ${v.retries}`}</Text>}
          </Text>
          <Text>
            <Text dimColor>{flow[0]}</Text>
            <Text color={tone}>{isLive ? ` ${FLOW_DOTS[tick % FLOW_DOTS.length]}▸ ` : ' ──▸ '}</Text>
            <Text bold>{worker ? worker.type : flow[1]}</Text>
            <Text color={tone}>{isLive ? ` ${FLOW_DOTS[(tick + 1) % FLOW_DOTS.length]}▸ ` : ' ──▸ '}</Text>
            <Text dimColor>{flow[2]}</Text>
          </Text>
          {worker && (
            <Box flexDirection="column">
              <Text dimColor>{`${worker.type} · ${elapsed(now - worker.firstSeen)} · ${worker.tools} tool calls`}</Text>
              {worker.recent.map((r, k) => (
                <Text dimColor={k > 0}>{clip(`  ↳ ${r}`, width - 2)}</Text>
              ))}
            </Box>
          )}
          {gateChain.length > 0 && (
            <Text>
              <Text dimColor>gate  </Text>
              {gateChain}
            </Text>
          )}
          {callout.head !== '' && <Text bold color={tone}>{callout.head}</Text>}
          {callout.body !== '' && <Text dimColor>{clip(callout.body, width * 2)}</Text>}
          {callout.actions.length > 0 && (
            <Box flexDirection="row" gap={1} marginTop={1}>
              {callout.actions.map(a => (
                <Button key={a.key} label={a.label} variant={a.primary ? 'primary' : 'secondary'} onPress={() => a.run()} />
              ))}
            </Box>
          )}
          {callout.hint !== '' && <Text dimColor>{callout.hint}</Text>}
        </Box>

        {mode === 'graph' ? (
          <Box flexDirection="column">
            {graphRows(v, width, tick, hot, tone).map(row => (
              <Text>{row.map(seg)}</Text>
            ))}
            {lastMove && (
              <Text color={hot ? 'claude' : undefined} bold={hot !== null} dimColor={hot === null}>
                {`${hot ? '' : 'last move  '}${moveCaption(lastMove)}`}
              </Text>
            )}
          </Box>
        ) : (
          <Box flexDirection="column">{v.phases.map((p, i) => phaseRow(p, i))}</Box>
        )}

        <Box flexDirection="row" gap={1}>
          <Button
            key="toggle-view"
            label={mode === 'graph' ? 'List' : 'Graph'}
            variant="secondary"
            onPress={() => update($, view, () => (mode === 'graph' ? 'list' : 'graph'))}
          />
          <Text dimColor>● done  ◉ now  ○ next   ✓ pass ✗ fail ⏸ you</Text>
        </Box>

        {list.length > 1 && (
          <Box flexDirection="column">
            <Text dimColor>Other runs</Text>
            {list.slice(1).map(o => (
              <Text dimColor>{summary(o)}</Text>
            ))}
          </Box>
        )}
      </Box>
    )
  })
}
