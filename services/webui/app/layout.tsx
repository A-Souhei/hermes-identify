import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'hermes-identify',
    template: '%s · hermes-identify',
  },
  description: 'Document ingestion, classification and entity extraction.',
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#fafbfd' },
    { media: '(prefers-color-scheme: dark)', color: '#0b1220' },
  ],
  colorScheme: 'light dark',
}

const themeInit = `(function(){try{var s=localStorage.getItem('hi-theme');var m=window.matchMedia('(prefers-color-scheme: dark)').matches;var d=s?s==='dark':m;document.documentElement.classList.toggle('dark',d);}catch(e){document.documentElement.classList.add('dark');}})();`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-screen antialiased bg-ink-950 text-ink-100 font-sans">
        <div className="relative min-h-screen">
          <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 bg-grid opacity-40" />
          <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-96 bg-ambient-top" />
          {children}
        </div>
      </body>
    </html>
  )
}
