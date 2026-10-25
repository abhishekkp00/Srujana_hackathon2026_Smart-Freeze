import React from 'react';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleDot,
  GitBranch,
  LockKeyhole,
  ScanSearch,
  Scale,
  ShieldCheck,
  Workflow,
} from 'lucide-react';
import './LandingPage.css';

interface DemoPersona {
  persona_id: string;
  display_name: string;
  role: string;
  assigned_case_count: number;
  institution_id: string;
}

interface LandingPageProps {
  demoEnabled: boolean;
  demoPersona: DemoPersona | null;
  starting: boolean;
  error: string | null;
  onEnterDemo: () => void;
}

const steps = [
  {
    number: '01',
    title: 'Reconstruct the trail',
    copy: 'Start with a source transaction. Follow later ledger events account by account, with timestamps and transaction references attached.',
  },
  {
    number: '02',
    title: 'Expose the uncertainty',
    copy: 'Compare Proportional, FIFO and LIBR. See where their assumptions produce different estimates instead of hiding disagreement.',
  },
  {
    number: '03',
    title: 'Propose a measured response',
    copy: 'Calculate a conservative account-level cap, inspect the inputs, and record a simulated hold proposal for human review.',
  },
];

export const LandingPage: React.FC<LandingPageProps> = ({
  demoEnabled,
  demoPersona,
  starting,
  error,
  onEnterDemo,
}) => {
  const canEnter = demoEnabled && Boolean(demoPersona) && !starting;

  const enterButton = (className: string, label: string) => (
    <button
      type="button"
      className={className}
      onClick={onEnterDemo}
      disabled={!canEnter}
    >
      {starting ? 'Opening workspace…' : label}
      {!starting && <ArrowRight size={16} strokeWidth={1.8} />}
    </button>
  );

  return (
    <div className="sf-landing">
      <header className="sf-site-header">
        <a className="sf-wordmark" href="#top" aria-label="Smart-Freeze home">
          <span className="sf-mark" aria-hidden="true">
            <svg viewBox="0 0 34 34" fill="none">
              <path d="M17 2.5 30.5 10v14L17 31.5 3.5 24V10L17 2.5Z" stroke="currentColor" strokeWidth="1.5" />
              <path d="M17 8 25.5 12.7v8.6L17 26l-8.5-4.7v-8.6L17 8Z" stroke="currentColor" strokeWidth="1.2" />
              <path d="M17 8v18M8.5 12.7 25.5 21.3M25.5 12.7 8.5 21.3" stroke="currentColor" strokeWidth="1.1" />
            </svg>
          </span>
          <span>Smart<span className="sf-wordmark-dash">-</span>Freeze</span>
        </a>

        <nav className="sf-top-nav" aria-label="Landing page navigation">
          <a href="#platform">Platform</a>
          <a href="#workflow">How it works</a>
          <a href="#governance">Governance</a>
        </nav>

        <div className="sf-header-cta">
          <span className="sf-local-label"><span className="sf-local-dot" /> Local demo</span>
          {enterButton('sf-button sf-button-small sf-button-dark', 'Open workspace')}
        </div>
      </header>

      <main id="top">
        <section className="sf-hero">
          <div className="sf-hero-copy">
            <div className="sf-eyebrow"><span className="sf-eyebrow-line" /> Financial investigation, made explainable</div>
            <h1>Trace the money.<br />Understand the risk.<br /><span>Hold with evidence.</span></h1>
            <p className="sf-hero-description">
              Smart-Freeze reconstructs suspicious fund flows, compares tracing methods,
              and shows how a measured hold proposal is derived — transaction by transaction.
            </p>

            <div className="sf-hero-actions">
              {enterButton('sf-button sf-button-primary', 'Explore the workspace')}
              <a className="sf-button sf-button-quiet" href="#workflow">See how it works <ArrowDownRight size={16} /></a>
            </div>

            {error && <div className="sf-inline-error" role="alert">{error}</div>}
            {!demoEnabled && (
              <div className="sf-inline-note">
                The workspace is unavailable because local demo authentication is not enabled in the backend.
              </div>
            )}

            <div className="sf-hero-footnote">
              <ShieldCheck size={15} strokeWidth={1.7} />
              <span>Decision support, not automated judgement. Demonstration uses synthetic ledger records.</span>
            </div>
          </div>

          <div className="sf-product-stage" aria-label="Illustrative Smart-Freeze transaction reconstruction preview">
            <div className="sf-stage-topline">
              <span className="sf-stage-window-label"><span className="sf-stage-window-dot" /> SMART-FREEZE / CASE WORKSPACE</span>
              <span className="sf-stage-case">CASE-2026-001</span>
            </div>

            <div className="sf-preview-window">
              <div className="sf-preview-toolbar">
                <div className="sf-preview-lights"><i /><i /><i /></div>
                <span>Money flow reconstruction</span>
                <span className="sf-preview-local">SYNTHETIC DATA</span>
              </div>

              <div className="sf-preview-heading">
                <div>
                  <span className="sf-preview-kicker">SOURCE TRANSACTION</span>
                  <h2>TXN_0009</h2>
                  <p>ACC_VICTIM_01 <ArrowRight size={13} /> ACC_MULE_DIRECT_01</p>
                </div>
                <div className="sf-preview-source-amount">
                  <span>Recorded amount</span>
                  <strong>₹1,00,000</strong>
                </div>
              </div>

              <div className="sf-flow-preview">
                <svg className="sf-flow-wires" viewBox="0 0 620 205" preserveAspectRatio="none" aria-hidden="true">
                  <path className="sf-wire sf-wire-source" d="M111 46 H225" />
                  <path className="sf-wire sf-wire-forward" d="M301 46 H413" />
                  <path className="sf-wire sf-wire-forward sf-wire-delay" d="M490 63 C490 111 472 129 418 129 H304" />
                  <path className="sf-wire sf-wire-context" d="M111 166 H225" />
                  <path className="sf-wire sf-wire-context" d="M301 166 H413" />
                  <path className="sf-wire sf-wire-forward" d="M489 63 C580 66 582 166 530 166" />
                  <path className="sf-wire-arrow" d="M217 40 L226 46 L217 52" />
                  <path className="sf-wire-arrow" d="M405 40 L414 46 L405 52" />
                  <path className="sf-wire-arrow" d="M313 123 L304 129 L313 135" />
                </svg>

                <div className="sf-flow-node sf-node-victim">
                  <span className="sf-node-type">SOURCE</span>
                  <strong>Victim account</strong>
                  <small>ACC_VICTIM_01</small>
                </div>
                <div className="sf-flow-node sf-node-flagged">
                  <span className="sf-node-type">CASE-LINKED</span>
                  <strong>Receiving account</strong>
                  <small>ACC_MULE_DIRECT_01</small>
                </div>
                <div className="sf-flow-node sf-node-commingled">
                  <span className="sf-node-type">COMMINGLED</span>
                  <strong>Shared balance</strong>
                  <small>ACC_COMMINGLED_01</small>
                </div>
                <div className="sf-flow-node sf-node-layer">
                  <span className="sf-node-type">FOLLOW-ON</span>
                  <strong>Downstream</strong>
                  <small>ACC_LAYER2_01</small>
                </div>
                <div className="sf-flow-amount sf-amount-one">₹1,00,000</div>
                <div className="sf-flow-amount sf-amount-two">₹80,000</div>
                <div className="sf-flow-amount sf-amount-three">₹60,000</div>

                <div className="sf-context-node">
                  <span className="sf-context-indicator" />
                  <span><strong>TXN_0014</strong><small>Later account credit · ₹40,000</small></span>
                </div>
                <div className="sf-context-caption">Context only — not attributed to the source lot</div>
              </div>

              <div className="sf-preview-footer">
                <div className="sf-preview-legend">
                  <span><i className="sf-legend-solid" /> Case-linked transfer</span>
                  <span><i className="sf-legend-dashed" /> Reachable path</span>
                  <span><i className="sf-legend-dotted" /> Account context</span>
                </div>
                <div className="sf-preview-disclaimer">Full recorded transfer amounts shown</div>
              </div>
            </div>

            <div className="sf-stage-caption">
              <span>01 / EXAMPLE CASE PATH</span>
              <span>Click through the workspace to inspect the underlying ledger records.</span>
            </div>
          </div>
        </section>

        <section className="sf-proof-strip" aria-label="Platform principles">
          <div className="sf-proof-intro">Built for decisions that need a paper trail.</div>
          <div className="sf-proof-item"><Check size={15} /><span>Source-linked transactions</span></div>
          <div className="sf-proof-item"><Check size={15} /><span>Three independent tracing methods</span></div>
          <div className="sf-proof-item"><Check size={15} /><span>Human review before action</span></div>
        </section>

        <section className="sf-dark-section" id="platform">
          <div className="sf-dark-grid">
            <div className="sf-dark-heading">
              <div className="sf-eyebrow sf-eyebrow-dark"><span className="sf-eyebrow-line" /> The platform</div>
              <h2>Not another fraud score.<br /><span>A trail you can explain.</span></h2>
              <p>
                A suspicious payment is only the beginning. Investigators need to see
                how funds moved, what remains uncertain, and why a proposed response is proportionate.
              </p>
              <a href="#workflow" className="sf-dark-link">Follow the process <ArrowUpRight size={16} /></a>
            </div>

            <div className="sf-dark-panel">
              <div className="sf-dark-panel-head">
                <span>CASE RECONSTRUCTION</span>
                <span className="sf-live-word"><i /> RECORD-BASED</span>
              </div>
              <div className="sf-timeline">
                <div className="sf-timeline-row">
                  <div className="sf-timeline-marker sf-marker-source"><CircleDot size={15} /></div>
                  <div className="sf-timeline-content">
                    <span className="sf-timeline-code">TXN_0009 · SOURCE</span>
                    <strong>Source transfer recorded</strong>
                    <p>Start from the case-linked event and its timestamp.</p>
                  </div>
                  <span className="sf-timeline-amount">₹1,00,000</span>
                </div>
                <div className="sf-timeline-connector" />
                <div className="sf-timeline-row">
                  <div className="sf-timeline-marker sf-marker-flag"><ScanSearch size={15} /></div>
                  <div className="sf-timeline-content">
                    <span className="sf-timeline-code">TXN_0010 · FOLLOW-ON</span>
                    <strong>Funds move to a commingled account</strong>
                    <p>Retain the complete transaction record; do not assume every rupee is traceable.</p>
                  </div>
                  <span className="sf-timeline-amount">₹80,000</span>
                </div>
                <div className="sf-timeline-connector" />
                <div className="sf-timeline-row">
                  <div className="sf-timeline-marker sf-marker-review"><Scale size={15} /></div>
                  <div className="sf-timeline-content">
                    <span className="sf-timeline-code">TRACE COMPARISON</span>
                    <strong>Compare three attribution assumptions</strong>
                    <p>Proportional, FIFO and LIBR expose where calculated amounts diverge.</p>
                  </div>
                  <span className="sf-timeline-side">3 methods</span>
                </div>
              </div>
              <div className="sf-dark-panel-foot">
                <LockKeyhole size={15} />
                <span>Any hold shown in the demo is a proposal only — no live account is changed.</span>
              </div>
            </div>
          </div>
        </section>

        <section className="sf-workflow-section" id="workflow">
          <div className="sf-section-header">
            <div>
              <div className="sf-eyebrow"><span className="sf-eyebrow-line" /> How Smart-Freeze works</div>
              <h2>From first alert<br />to a reviewable decision.</h2>
            </div>
            <p>Each stage is tied to underlying records and calculations. The investigator can inspect the evidence instead of accepting a black-box outcome.</p>
          </div>

          <div className="sf-steps-grid">
            {steps.map((step, index) => (
              <article className="sf-step" key={step.number}>
                <div className="sf-step-top"><span>{step.number}</span><span className="sf-step-icon">{index === 0 ? <GitBranch size={19} /> : index === 1 ? <Scale size={19} /> : <LockKeyhole size={19} />}</span></div>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
                <div className="sf-step-rule" />
              </article>
            ))}
          </div>
        </section>

        <section className="sf-governance-section" id="governance">
          <div className="sf-governance-mark"><ShieldCheck size={22} strokeWidth={1.5} /></div>
          <div className="sf-governance-copy">
            <div className="sf-eyebrow sf-eyebrow-dark"><span className="sf-eyebrow-line" /> Responsible by design</div>
            <h2>Measure carefully.<br />Keep a human in control.</h2>
            <p>
              A tracing estimate is not proof of guilt, and a proposed hold is not a freeze.
              Smart-Freeze keeps model signals separate from fund-tracing calculations and presents
              method assumptions for authorized review.
            </p>
          </div>
          <div className="sf-governance-list">
            <div><Check size={15} /><span>Exact-paise ledger calculations</span></div>
            <div><Check size={15} /><span>Visible method disagreement</span></div>
            <div><Check size={15} /><span>Auditable simulated hold proposals</span></div>
            <div><Check size={15} /><span>No automatic account freezing</span></div>
          </div>
        </section>

        <section className="sf-final-cta">
          <div>
            <div className="sf-eyebrow"><span className="sf-eyebrow-line" /> Smart-Freeze</div>
            <h2>Follow the money.<br />Review the evidence.</h2>
            <p>Open the local workspace to inspect a case, trace the movement, and step through a simulated hold proposal.</p>
          </div>
          {enterButton('sf-button sf-button-primary', 'Enter the workspace')}
        </section>
      </main>

      <footer className="sf-site-footer">
        <a className="sf-wordmark sf-wordmark-footer" href="#top">
          <span className="sf-mark" aria-hidden="true">
            <svg viewBox="0 0 34 34" fill="none">
              <path d="M17 2.5 30.5 10v14L17 31.5 3.5 24V10L17 2.5Z" stroke="currentColor" strokeWidth="1.5" />
              <path d="M17 8 25.5 12.7v8.6L17 26l-8.5-4.7v-8.6L17 8Z" stroke="currentColor" strokeWidth="1.2" />
              <path d="M17 8v18M8.5 12.7 25.5 21.3M25.5 12.7 8.5 21.3" stroke="currentColor" strokeWidth="1.1" />
            </svg>
          </span>
          <span>Smart<span className="sf-wordmark-dash">-</span>Freeze</span>
        </a>
        <span>Fund-tracing decision support</span>
        <span className="sf-footer-note">Synthetic data demonstration · Not connected to a bank</span>
      </footer>
    </div>
  );
};

export default LandingPage;
