import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'

const SECTIONS = [
  { id: 'overview', title: 'Overview' },
  { id: 'data-collected', title: 'Data We Collect' },
  { id: 'usage', title: 'How We Use Data' },
  { id: 'retention', title: 'Data Retention' },
  { id: 'gdpr', title: 'Your Rights (GDPR)' },
  { id: 'cookies', title: 'Cookies' },
  { id: 'security', title: 'Security' },
  { id: 'contact', title: 'Contact Us' },
]

export default function Privacy() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <BrandMark />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={() => window.history.back()}>
              <ArrowLeft className="mr-1.5 size-3.5" /> Back
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
          {/* Sidebar TOC */}
          <aside className="hidden lg:block">
            <div className="sticky top-24 rounded-lg border bg-card p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Contents</p>
              <nav className="flex flex-col gap-1">
                {SECTIONS.map(s => (
                  <a
                    key={s.id}
                    href={`#${s.id}`}
                    className="rounded px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                  >
                    {s.title}
                  </a>
                ))}
              </nav>
            </div>
          </aside>

          {/* Prose content */}
          <article className="prose prose-sm max-w-none dark:prose-invert">
            <h1 className="text-3xl font-bold tracking-tight">Privacy Policy</h1>
            <p className="text-muted-foreground">Last updated: {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</p>

            <section id="overview" className="mt-10">
              <h2 className="text-xl font-bold">Overview</h2>
              <p>Panopta ("we", "our", "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and safeguard information when you use our data quality monitoring platform at panopta.app.</p>
              <p>By using Panopta, you agree to the collection and use of information in accordance with this policy.</p>
            </section>

            <section id="data-collected" className="mt-10">
              <h2 className="text-xl font-bold">Data We Collect</h2>
              <h3 className="text-base font-semibold mt-4">Account information</h3>
              <p>When you create a Panopta account, we collect your name, email address, and encrypted password. We do not store plaintext passwords.</p>
              <h3 className="text-base font-semibold mt-4">Database connection credentials</h3>
              <p>Panopta stores connection credentials (host, username, password) you provide to connect your databases. All credentials are encrypted using HKDF-derived per-tenant Fernet keys — your credentials are never stored in plaintext and cannot be decrypted by other tenants or without the master encryption key.</p>
              <h3 className="text-base font-semibold mt-4">Database metadata and statistics</h3>
              <p>Panopta executes read-only queries against your databases to collect aggregate metrics: row counts, null rates, column cardinalities, min/max values, and schema structure. We never read, copy, or store the actual content of your database rows.</p>
              <h3 className="text-base font-semibold mt-4">Usage data</h3>
              <p>We may collect information about how you use the Panopta interface (page views, feature usage) for improving the product. We do not sell this data to third parties.</p>
            </section>

            <section id="usage" className="mt-10">
              <h2 className="text-xl font-bold">How We Use Data</h2>
              <ul>
                <li>To provide the data quality monitoring service you signed up for</li>
                <li>To detect anomalies and generate incident reports for your databases</li>
                <li>To send you alert notifications and digest emails (based on your preferences)</li>
                <li>To improve the Panopta platform and fix bugs</li>
                <li>To send transactional emails (invites, password resets, welcome messages)</li>
              </ul>
              <p>We do not sell, trade, or rent your personal information to third parties.</p>
            </section>

            <section id="retention" className="mt-10">
              <h2 className="text-xl font-bold">Data Retention</h2>
              <p>Profile history retention depends on your plan:</p>
              <ul>
                <li><strong>Free plan:</strong> 7 days of profile history</li>
                <li><strong>Starter plan:</strong> 90 days of profile history</li>
                <li><strong>Growth plan:</strong> 1 year of profile history</li>
                <li><strong>Enterprise plan:</strong> Indefinite retention</li>
              </ul>
              <p>When you delete a data source, profile history is preserved for trend analysis but the source is marked as paused. When you close your Panopta account, all your data is deleted within 30 days.</p>
            </section>

            <section id="gdpr" className="mt-10">
              <h2 className="text-xl font-bold">Your Rights (GDPR)</h2>
              <p>If you are located in the European Union, you have the following rights under GDPR:</p>
              <ul>
                <li><strong>Right of access:</strong> Request a copy of the personal data we hold about you.</li>
                <li><strong>Right to rectification:</strong> Request correction of inaccurate personal data.</li>
                <li><strong>Right to erasure:</strong> Request deletion of your personal data ("right to be forgotten").</li>
                <li><strong>Right to restriction:</strong> Request that we limit how we process your data.</li>
                <li><strong>Right to portability:</strong> Request your data in a portable format.</li>
                <li><strong>Right to object:</strong> Object to processing of your personal data.</li>
              </ul>
              <p>To exercise any of these rights, contact us at privacy@panopta.app.</p>
            </section>

            <section id="cookies" className="mt-10">
              <h2 className="text-xl font-bold">Cookies</h2>
              <p>Panopta uses minimal cookies — only those strictly necessary for authentication (JWT session token stored in localStorage, not cookies) and security (CSRF tokens). We do not use advertising or tracking cookies.</p>
            </section>

            <section id="security" className="mt-10">
              <h2 className="text-xl font-bold">Security</h2>
              <p>Security is a core design principle of Panopta:</p>
              <ul>
                <li>All credentials encrypted with HKDF per-tenant Fernet keys</li>
                <li>Read-only database connections — Panopta cannot modify your data</li>
                <li>JWT authentication with 15-minute token expiry</li>
                <li>API key authentication hashed with bcrypt</li>
                <li>Query timeouts to protect production databases</li>
                <li>HTTPS-only in production</li>
              </ul>
              <p>If you discover a security vulnerability, please contact us at security@panopta.app.</p>
            </section>

            <section id="contact" className="mt-10">
              <h2 className="text-xl font-bold">Contact Us</h2>
              <p>If you have any questions about this Privacy Policy or your data, contact us:</p>
              <ul>
                <li>Email: privacy@panopta.app</li>
                <li>Subject line: "Privacy Request — [your request type]"</li>
              </ul>
            </section>
          </article>
        </div>
      </div>

      <footer className="border-t py-6 mt-12">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4">
          <BrandMark iconOnly />
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Panopta. All rights reserved.</p>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <a href="/terms" className="hover:text-foreground">Terms</a>
            <a href="/privacy" className="hover:text-foreground">Privacy</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
