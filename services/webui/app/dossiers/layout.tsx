import { Sidebar } from '@/components/Sidebar'

export default function DossiersLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col lg:flex-row min-h-screen">
      <Sidebar active="dossiers" />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}
