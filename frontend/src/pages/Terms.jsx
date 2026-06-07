import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'

const SECTIONS = [
  { id: 'overview', title: 'Overview' },
  { id: 'acceptable-use', title: 'Acceptable Use' },
  { id: 'data-ownership', title: 'Data Ownership' },
  { id: 'availability', title: 'Service Availability' },
  { id: 'billing', title: 'Billing Terms' },
  { id: 'liability', title: 'Limitation of Liability' },
  { id: 'termination', title: 'Termination' },
  { id: 'changes', title: 'Changes to Terms' },
  { id: 'governing-law', title: 'Governing Law' },
  { id: 'contact', title: 'Contact' },
]

export default function Terms() {
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
            <h1 className="text-3xl font-bold tracking-tight">Terms of Service</h1>
            <p className="text-muted-foreground">Last updated: {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</p>

            <section id="overview" className="mt-10">
              <h2 className="text-xl font-bold">Overview</h2>
              <p>These Terms of Service ("Terms") govern your use of Panopta ("Service"), a data quality monitoring platform operated at panopta.app. By creating an account or accessing the Service, you agree to be bound by these Terms.</p>
              <p>If you are using Panopta on behalf of an organization, you represent that you have authority to bind that organization to these Terms, and references to "you" include both you personally and the organization.</p>
              <p>Please read these Terms carefully. If you disagree with any part, you may not use the Service.</p>
            </section>

            <section id="acceptable-use" className="mt-10">
              <h2 className="text-xl font-bold">Acceptable Use</h2>
              <p>You may use Panopta only for lawful purposes and in accordance with these Terms. You agree not to:</p>
              <ul>
                <li>Use the Service to monitor databases you do not own or have explicit authorization to access</li>
                <li>Attempt to gain unauthorized access to the Service, other users' accounts, or Panopta's infrastructure</li>
                <li>Use the Service to store, transmit, or process personal data in violation of applicable privacy laws (GDPR, CCPA, etc.)</li>
                <li>Interfere with or disrupt the integrity or performance of the Service or its connected infrastructure</li>
                <li>Reverse engineer, decompile, or attempt to extract the source code of the Service</li>
                <li>Use the Service to perform competitive intelligence against Panopta or to build a competing product</li>
                <li>Resell, sublicense, or otherwise make the Service available to third parties without prior written consent</li>
                <li>Use the Service in any manner that could disable, overburden, or impair the Service</li>
              </ul>
              <p>Panopta reserves the right to investigate suspected violations and to suspend or terminate accounts engaged in prohibited activities without notice.</p>
            </section>

            <section id="data-ownership" className="mt-10">
              <h2 className="text-xl font-bold">Data Ownership</h2>
              <h3 className="text-base font-semibold mt-4">Your data remains yours</h3>
              <p>You retain all ownership rights to your databases, connection credentials, and the aggregate statistics Panopta collects about your databases. Panopta does not claim any ownership over your data.</p>
              <h3 className="text-base font-semibold mt-4">License to operate the Service</h3>
              <p>By connecting a database to Panopta, you grant us a limited, non-exclusive license to execute read-only queries against your database solely for the purpose of providing the monitoring service described herein. This license is revocable by disconnecting the data source.</p>
              <h3 className="text-base font-semibold mt-4">What we collect</h3>
              <p>Panopta collects only aggregate statistical metrics from your databases (row counts, null rates, column cardinalities, schema structure, etc.). We never read, copy, store, or process the actual row-level content of your database tables.</p>
              <h3 className="text-base font-semibold mt-4">Data portability</h3>
              <p>You may export your profile history, incident records, and alert configurations at any time from your account settings. On account closure, we will provide a data export upon request within 14 days before deleting your data.</p>
            </section>

            <section id="availability" className="mt-10">
              <h2 className="text-xl font-bold">Service Availability</h2>
              <p>Panopta aims to provide a reliable, high-availability service, but we do not guarantee uninterrupted operation. We will endeavor to:</p>
              <ul>
                <li>Provide at least 99% uptime for paid plans, measured monthly</li>
                <li>Notify customers of planned maintenance at least 24 hours in advance via email</li>
                <li>Restore service within 4 hours in the event of an unplanned outage</li>
              </ul>
              <p>Downtime caused by factors outside our reasonable control (including network failures, third-party service outages, or force majeure events) is excluded from uptime calculations.</p>
              <p>The Service is provided "as is" without warranty of any kind. We reserve the right to modify, suspend, or discontinue any feature of the Service with reasonable notice.</p>
            </section>

            <section id="billing" className="mt-10">
              <h2 className="text-xl font-bold">Billing Terms</h2>
              <h3 className="text-base font-semibold mt-4">Subscription plans</h3>
              <p>Panopta offers Free, Starter ($49/month), Growth ($149/month), and Agency ($299/month) plans. Plan features and limits are described on the pricing page. You may upgrade, downgrade, or cancel at any time.</p>
              <h3 className="text-base font-semibold mt-4">Payment and billing cycle</h3>
              <p>Paid subscriptions are billed monthly in advance. Annual subscriptions receive a 20% discount and are billed annually in advance. All prices are in USD.</p>
              <h3 className="text-base font-semibold mt-4">Cancellation and refunds</h3>
              <p>You may cancel your subscription at any time from Settings → Billing. Cancellation takes effect at the end of the current billing period — you retain access to paid features until then. We do not issue refunds for partial billing periods.</p>
              <h3 className="text-base font-semibold mt-4">Failed payments</h3>
              <p>If a payment fails, we will attempt to charge the payment method again after 3 days. If payment is not received within 7 days of the initial failure, your account will be downgraded to the Free plan. No data is deleted during this grace period.</p>
              <h3 className="text-base font-semibold mt-4">Plan limits</h3>
              <p>Exceeding plan limits (sources, tables) will result in a 402 response on the relevant API calls. We will not automatically charge or upgrade your plan. You must upgrade manually to continue adding resources beyond your plan limit.</p>
            </section>

            <section id="liability" className="mt-10">
              <h2 className="text-xl font-bold">Limitation of Liability</h2>
              <p>To the maximum extent permitted by applicable law:</p>
              <ul>
                <li>Panopta is provided "as is" and "as available" without warranties of any kind, express or implied.</li>
                <li>Panopta does not warrant that the Service will be error-free, uninterrupted, or that detected anomalies are complete or accurate.</li>
                <li>In no event shall Panopta be liable for indirect, incidental, special, consequential, or punitive damages arising from your use of or inability to use the Service.</li>
                <li>Our total liability to you for any claim arising from these Terms or the Service shall not exceed the amount paid by you to Panopta in the 12 months preceding the claim.</li>
              </ul>
              <p>Some jurisdictions do not allow exclusion of certain warranties or limitation of liability. In such jurisdictions, our liability is limited to the fullest extent permitted by law.</p>
            </section>

            <section id="termination" className="mt-10">
              <h2 className="text-xl font-bold">Termination</h2>
              <h3 className="text-base font-semibold mt-4">Termination by you</h3>
              <p>You may close your account at any time from Settings → Account. Your data will be deleted within 30 days of account closure. Cancellation of a paid plan does not automatically close your account — you continue to have a free account.</p>
              <h3 className="text-base font-semibold mt-4">Termination by Panopta</h3>
              <p>We may suspend or terminate your account if you violate these Terms, engage in fraudulent or illegal activity, or if we determine that your use poses a security risk to other users. In the event of termination for cause, we are not obligated to provide a data export or refund.</p>
              <h3 className="text-base font-semibold mt-4">Effect of termination</h3>
              <p>Upon termination, your access to the Service will cease immediately. Provisions of these Terms that by their nature should survive termination (including Limitation of Liability and Governing Law) will survive.</p>
            </section>

            <section id="changes" className="mt-10">
              <h2 className="text-xl font-bold">Changes to Terms</h2>
              <p>We may update these Terms from time to time. When we make material changes, we will:</p>
              <ul>
                <li>Update the "Last updated" date at the top of this page</li>
                <li>Send an email notification to all registered users at least 14 days before the changes take effect</li>
                <li>Display a notice in the Panopta dashboard</li>
              </ul>
              <p>Your continued use of the Service after the effective date of updated Terms constitutes acceptance of the new Terms. If you disagree with the changes, you must stop using the Service and close your account before the effective date.</p>
            </section>

            <section id="governing-law" className="mt-10">
              <h2 className="text-xl font-bold">Governing Law</h2>
              <p>These Terms shall be governed by and construed in accordance with applicable law. Any disputes arising from these Terms or the Service shall be resolved through binding arbitration or in courts of competent jurisdiction.</p>
              <p>If any provision of these Terms is found to be unenforceable, the remaining provisions will remain in full force and effect. Our failure to enforce any provision of these Terms shall not be construed as a waiver of such provision.</p>
            </section>

            <section id="contact" className="mt-10">
              <h2 className="text-xl font-bold">Contact</h2>
              <p>If you have questions about these Terms or need to report a violation, contact us:</p>
              <ul>
                <li>Email: legal@panopta.app</li>
                <li>Subject line: "Terms Inquiry — [your request]"</li>
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
