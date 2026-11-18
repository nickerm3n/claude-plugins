import { expect, test } from 'claude-code/testing'

import { detectMove, graphRows, moveCaption, toView } from '../hooks/pane'

const PHASES = ['task', 'enrich', 'research', 'design', 'qa-plan', 'plan', 'code', 'qa-check', 'deploy', 'qa']

function view(current: string, extra: object = {}) {
  const at = PHASES.indexOf(current)
  return toView(
    {
      key: 'PROJ-1',
      status: 'running',
      pipeline: 'feature',
      current,
      phases: PHASES,
      phase_status: Object.fromEntries(PHASES.slice(0, at).map(p => [p, 'passed'])),
      retries: {},
      plan_step: null,
      pr: null,
      ...extra,
    },
    '',
  )
}

const text = (rows: { t: string }[][]) => rows.map(r => r.map(s => s.t).join(''))

test('a move is an advance, a rewind or a retry, and nothing otherwise', async () => {
  expect(detectMove(undefined, view('design'), 1)).toBeNull()
  expect(detectMove(view('design'), view('design'), 1)).toBeNull()
  expect(detectMove(view('design'), view('qa-plan'), 7)).toEqual({ key: 'PROJ-1', from: 'design', to: 'qa-plan', kind: 'advance', at: 7 })
  expect(detectMove(view('code'), view('design'), 7)?.kind).toBe('rewind')
  expect(detectMove(view('code'), view('code', { retries: { code: 1 } }), 7)?.kind).toBe('retry')
  expect(moveCaption({ key: 'PROJ-1', from: 'design', to: 'qa-plan', kind: 'advance', at: 0 })).toBe('Design ✓ ▸ QA Plan')
})

test('the edge a run just crossed lights up, the others stay plain', async () => {
  const move = { key: 'PROJ-1', from: 'design', to: 'qa-plan', kind: 'advance' as const, at: 0 }
  const even = text(graphRows(view('qa-plan'), 44, 0, move, 'claude'))[0]
  const odd = text(graphRows(view('qa-plan'), 44, 1, move, 'claude'))[0]
  expect(even).toContain('●━▸◉')
  expect(odd).not.toContain('▸')
  expect(odd.startsWith('●━━●━━●━━●━━')).toBe(true)
})

test('a narrow pane squeezes the edges instead of wrapping', async () => {
  const rows = text(graphRows(view('code'), 20, 1, null, 'claude'))
  expect(rows[0].length).toBe(19)
  expect(rows[1]).toContain('Code · running ▲')
})
