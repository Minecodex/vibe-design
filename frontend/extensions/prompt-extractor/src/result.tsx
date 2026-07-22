import { createRoot } from 'react-dom/client'

import { PromptResultView, PromptResultViewProps, queryPromptJobId } from './PromptResultView'

export function PromptResultApp(props: Omit<PromptResultViewProps, 'mode'>) {
  return <PromptResultView {...props} jobId={props.jobId || queryPromptJobId()} mode="page" />
}

const rootElement = document.getElementById('root')
if (rootElement) {
  createRoot(rootElement).render(<PromptResultApp />)
}
