// Test-only helper: fold a sequence of legacy home-harness events through
// `applyHomeHarnessEvent`. This used to be exported from the production
// `homeHarnessProjection` module, but it is only ever used by tests (the live
// runtime applies events one-at-a-time behind the runtime-adapter gate, and
// reloads hydrate from persisted snapshots), so it lives here instead.
import {
  applyHomeHarnessEvent,
  createHomeHarnessProjectionState,
  type HomeHarnessProjectionEvent,
  type HomeHarnessProjectionState,
} from '../homeHarnessProjection'

export function replayHomeHarnessEvents(
  events: HomeHarnessProjectionEvent[],
  initialState: HomeHarnessProjectionState = createHomeHarnessProjectionState(),
): HomeHarnessProjectionState {
  return events.reduce((state, event) => applyHomeHarnessEvent(state, event), initialState)
}
