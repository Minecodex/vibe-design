import { ChatSidebarShell } from './components/ChatSidebarShell'
import { useChatSidebar, type ChatSidebarProps } from './hooks/useChatSidebar'

export function ChatSidebar(props: ChatSidebarProps) {
  const viewModel = useChatSidebar(props)
  return <ChatSidebarShell {...viewModel} />
}
