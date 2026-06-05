import { Sidebar } from '@/components/Sidebar'

export default function TopicsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <Sidebar active="topics" />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}
