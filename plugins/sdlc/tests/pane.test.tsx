import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

const PHASES = ['task', 'enrich', 'research', 'design', 'qa-plan', 'plan', 'code', 'qa-check', 'deploy', 'qa']

const RUN = {
  key: 'PROJ-2553',
  status: 'waiting_human',
  pipeline: 'feature',
  current: 'design',
  phases: PHASES,
  phase_status: { task: 'passed', enrich: 'passed', research: 'passed', design: 'waiting' },
  retries: {},
  plan_step: null,
  pr: null,
  updated_at: '2026-11-09T10:00:00Z',
  gate_plan: { task: ['code'], enrich: ['code', 'human'], research: ['code'], design: ['code', 'human'], code: ['code', 'judge'] },
  gates: {
    task: { code: { status: 'pass' } },
    enrich: { code: { status: 'pass' }, human: { status: 'approved' } },
    research: { code: { status: 'pass' } },
    design: { code: { status: 'pass' }, human: { status: 'waiting', detail: 'design review' } },
  },
  history: [{ phase: 'design', event: 'wait', detail: 'design review in the session' }],
}

const PANE = {
  plugin: 'sdlc',
  component: 'Pane',
  requestId: 'sdlc-runs',
  props: {
    title: 'AI SDLC',
    isFocused: false,
    bodyColumns: 44,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

function engine(on: Parameters<TestBody>[1], run: object | null, ran: string[]) {
  on('command.register', () => ({ value: { command: 'sdlc-pane' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.every', () => ({ value: undefined }))
  on('fs.exists', () => ({ value: run !== null }))
  on('fs.list', () => ({ value: [{ name: 'PROJ-2553', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }))
  on('fs.read', (_, e) => ({
    value: String(e.path).endsWith('01-task.md') ? '# PROJ-2553 · Send reminder emails\n' : JSON.stringify(run),
  }))
  on('command.run', (_, e) => {
    ran.push(`/${e.command} ${e.args}`.trim())
    return { text: 'ok' }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('clock.now', () => ({ value: 100_000 }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1_000_000, percent: 42 }, rateLimits: [], cost: { usd: 1.84 } } }))
  on('agent.list', () => ({ value: [{ id: 'a1', description: 'research PROJ-2553', type: 'sdlc:researcher', status: 'running' }] }))
  on('tool.call', () => ({ result: {} }))
}

test('the pane draws the run as a gate state machine, on every surface', async ($, on) => {
  engine(on, RUN, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /Send reminder/ }))?.text).toBe('Send reminder emails')
    expect((await ui.find({ type: 'Text', text: /Review the design/ }))?.text).toBe('Review the design')
    expect((await ui.find({ type: 'Text', text: /●━━●━━●━━◐┈┈○┈┈○┈┈○┈┈○┈┈○┈┈○/ }))).toBeDefined()
    expect((await ui.find({ type: 'Text', text: /▲ Design · waiting for you/ }))).toBeDefined()
    await ui.press({ key: 'toggle-view' })
    expect((await ui.find({ type: 'Text', text: /● Research/ }))?.text).toContain('Research')
    expect((await ui.find({ type: 'Text', text: /Design\s+◀ waiting for you/ }))).toBeDefined()
    await ui.press({ key: 'toggle-view' })
    expect((await ui.find({ type: 'Text', text: /✓ code ──▸ ⏸ you/ }))).toBeDefined()
    expect((await ui.find({ type: 'Text', text: /\$1\.84/ }))?.text).toContain('context 42%')
    expect((await ui.find({ type: 'Text', text: /3\/10/ }))?.text).toContain('3/10')
    await ui.unmount()
  }
})

test('Approve design runs /sdlc:approve design', async ($, on) => {
  const ran: string[] = []
  engine(on, RUN, ran)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'approve-design' })
  expect(ran).toEqual(['/sdlc:approve design'])
  await ui.unmount()
})

test('an escalated code phase offers a retry and shows the failed gate step', async ($, on) => {
  const escalated = {
    ...RUN,
    status: 'escalated',
    current: 'code',
    plan_step: 2,
    retries: { code: 4 },
    phase_status: { ...RUN.phase_status, design: 'passed', 'qa-plan': 'passed', plan: 'passed', code: 'escalated' },
    gates: { ...RUN.gates, code: { code: { status: 'fail', detail: '2 violation(s)' }, judge: { status: 'pending' } } },
    history: [{ phase: 'code', event: 'escalate', detail: 'retry 4 > max_retries 3: yarn test:ci failed' }],
  }
  const ran: string[] = []
  engine(on, escalated, ran)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /needs your decision/ }))?.text).toBe('Code needs your decision')
  expect((await ui.find({ type: 'Text', text: /✗ code/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /yarn test:ci failed/ }))).toBeDefined()
  await ui.press({ key: 'continue' })
  expect(ran).toEqual(['/sdlc:approve code'])
  await ui.unmount()
})

test('the running agent and what it does show in the Now card', async ($, on) => {
  const running = {
    ...RUN,
    status: 'running',
    current: 'research',
    phase_status: { task: 'passed', enrich: 'passed', research: 'running' },
    gates: { ...RUN.gates, research: { code: { status: 'pending' } } },
    history: [{ phase: 'research', event: 'start' }],
  }
  engine(on, running, [])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.tool.call({ tool: 'Bash', command: 'rg -n "reminder" src', agentId: 'a1' })
  await $.tool.call({ tool: 'Read', file_path: 'src/entities/CorporateClient.ts', agentId: 'a1' })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /researcher · .* · 2 tool calls/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /↳ read src\/entities\/CorporateClient\.ts/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /↳ search "reminder"/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /task\+enrich\+code.*researcher.*03-research/ }))).toBeDefined()
  await ui.unmount()
})

test('no runs: the pane says how to start one', async ($, on) => {
  engine(on, null, [])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /No pipeline runs/ }))?.text).toBe('No pipeline runs yet')
  await ui.unmount()
})

const WITH_REWIND = {
  ...RUN,
  status: 'running',
  current: 'design',
  phase_status: { task: 'passed', enrich: 'passed', research: 'passed', design: 'running' },
  retries: { design: 1 },
  history: [
    { phase: 'code', event: 'fail', detail: 'retry 1/3: tests' },
    { phase: 'design', event: 'rewind', detail: 'the judge found a design issue' },
  ],
}

test('a rewind draws a dashed-back arc and the retry count is on the pointer', async ($, on) => {
  engine(on, { ...WITH_REWIND, current: 'design', phases: PHASES }, [])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /▴─+╯ rewind/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /Design · running ↺1/ }))).toBeDefined()
  await ui.unmount()
})

test('a design issue from the judge draws an arc from code back to design', async ($, on) => {
  const issue = {
    ...RUN,
    status: 'waiting_human',
    current: 'code',
    phase_status: { ...RUN.phase_status, design: 'passed', 'qa-plan': 'passed', plan: 'passed', code: 'waiting' },
    gates: { ...RUN.gates, code: { code: { status: 'pass' }, judge: { status: 'DESIGN_ISSUE', detail: 'wrong aggregate' } } },
    history: [{ phase: 'code', event: 'wait', detail: 'design issue: wrong aggregate' }],
  }
  engine(on, issue, [])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /▴─+╯ design issue/ }))).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /▲ Code · waiting for you/ }))).toBeDefined()
  await ui.unmount()
})
