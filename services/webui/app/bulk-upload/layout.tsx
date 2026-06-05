import { Sidebar } from '@/components/Sidebar'

export default function BulkUploadLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <Sidebar active="bulk-upload" />
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}
