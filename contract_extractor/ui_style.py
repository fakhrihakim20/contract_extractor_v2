from __future__ import annotations

from html import escape

import streamlit as st


def inject_clean_ui() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;650;700&family=Outfit:wght@400;520;650;760;820&display=swap');

        :root {
          --accent: #285571;
          --accent-ink: #17384d;
          --accent-soft: #e6eef3;
          --bg: #f6f8fb;
          --surface: rgba(255, 255, 255, 0.9);
          --surface-solid: #ffffff;
          --text: #111827;
          --muted: #64748b;
          --line: rgba(100, 116, 139, 0.22);
          --line-strong: rgba(40, 85, 113, 0.24);
          --shadow: 0 24px 80px -56px rgba(17, 24, 39, 0.52);
          --shadow-tight: 0 14px 35px -28px rgba(17, 24, 39, 0.42);
        }

        * {
          letter-spacing: 0 !important;
        }

        html,
        body,
        .stApp,
        [class*="css"] {
          font-family: "Outfit", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
        }

        .stApp {
          background:
            linear-gradient(120deg, rgba(40, 85, 113, 0.08), transparent 36%),
            linear-gradient(180deg, #fbfcfd 0%, var(--bg) 44%, #eef3f7 100%);
          color: var(--text);
        }

        [data-testid="stHeader"] {
          background: rgba(246, 248, 251, 0.82);
          backdrop-filter: blur(14px) saturate(120%);
          -webkit-backdrop-filter: blur(14px) saturate(120%);
        }

        .block-container {
          max-width: 1320px;
          padding-top: 1.55rem;
          padding-bottom: 2.8rem;
        }

        h1, h2, h3 {
          color: var(--text) !important;
          font-weight: 760 !important;
        }

        p,
        .stMarkdown,
        label {
          color: var(--text);
        }

        code,
        pre,
        .metric-value,
        [data-testid="stMetricValue"],
        [data-testid="stDataFrame"] {
          font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
        }

        .app-hero {
          position: relative;
          display: grid;
          grid-template-columns: minmax(0, 1.42fr) minmax(320px, 0.58fr);
          gap: 1.2rem;
          align-items: stretch;
          margin: 0 0 1rem 0;
        }

        .hero-copy {
          min-height: 220px;
          padding: 2rem 2.1rem;
          border: 1px solid var(--line);
          border-radius: 8px;
          background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(246, 248, 251, 0.88)),
            radial-gradient(circle at 12% 0%, rgba(40, 85, 113, 0.1), transparent 34%);
          box-shadow: var(--shadow);
          overflow: hidden;
        }

        .hero-kicker {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--accent);
          font-size: 0.74rem;
          font-weight: 820;
          text-transform: uppercase;
        }

        .hero-kicker::before {
          content: "";
          width: 0.45rem;
          height: 0.45rem;
          border-radius: 999px;
          background: var(--accent);
          box-shadow: 0 0 0 5px rgba(40, 85, 113, 0.1);
          animation: breath 2.8s cubic-bezier(0.16, 1, 0.3, 1) infinite;
        }

        .hero-title {
          max-width: 13ch;
          margin: 0.62rem 0 0 0;
          font-size: clamp(2.25rem, 5.2vw, 5.1rem);
          font-weight: 820;
          line-height: 0.92;
          color: var(--text);
        }

        .hero-subtitle {
          max-width: 66ch;
          margin-top: 1rem;
          color: #475569;
          font-size: 1rem;
          line-height: 1.7;
        }

        .hero-panel {
          position: relative;
          min-height: 220px;
          border: 1px solid var(--line-strong);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.72);
          box-shadow: var(--shadow);
          overflow: hidden;
        }

        .flow-rail {
          position: absolute;
          inset: 1.25rem;
          display: grid;
          grid-template-rows: repeat(4, 1fr);
          gap: 0.7rem;
        }

        .flow-step {
          position: relative;
          display: grid;
          grid-template-columns: 2.4rem 1fr;
          gap: 0.72rem;
          align-items: center;
          padding: 0.72rem;
          border: 1px solid rgba(40, 85, 113, 0.16);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.78);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
          transform: translateY(8px);
          opacity: 0;
          animation: rise 520ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
          animation-delay: calc(var(--step) * 90ms);
        }

        .flow-node {
          display: grid;
          place-items: center;
          width: 2.2rem;
          height: 2.2rem;
          border-radius: 999px;
          background: var(--accent-soft);
          color: var(--accent-ink);
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 0.76rem;
          font-weight: 760;
        }

        .flow-label {
          color: var(--text);
          font-size: 0.92rem;
          font-weight: 700;
          line-height: 1.15;
        }

        .flow-meta {
          margin-top: 0.15rem;
          color: var(--muted);
          font-size: 0.75rem;
          line-height: 1.25;
        }

        .metric-strip {
          display: grid;
          grid-template-columns: 1.15fr 0.85fr 0.85fr 1.15fr;
          gap: 0.78rem;
          margin: 0.9rem 0 1.1rem;
        }

        .metric-box {
          position: relative;
          min-height: 88px;
          padding: 0.95rem 1rem;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.86);
          box-shadow: var(--shadow-tight);
          overflow: hidden;
        }

        .metric-box::before {
          content: "";
          position: absolute;
          inset: 0 auto 0 0;
          width: 3px;
          background: var(--accent);
          opacity: 0.72;
        }

        .metric-label {
          color: var(--muted);
          font-size: 0.73rem;
          font-weight: 720;
          text-transform: uppercase;
        }

        .metric-value {
          color: var(--text);
          font-size: 1.35rem;
          font-weight: 760;
          margin-top: 0.2rem;
          overflow-wrap: anywhere;
        }

        .section-intro {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 1rem;
          align-items: end;
          margin: 0.35rem 0 0.95rem;
          padding: 0 0 0.85rem;
          border-bottom: 1px solid var(--line);
        }

        .section-intro h2 {
          margin: 0;
          font-size: clamp(1.35rem, 2vw, 1.85rem);
          line-height: 1;
        }

        .section-intro p {
          max-width: 74ch;
          margin: 0.45rem 0 0;
          color: var(--muted);
          line-height: 1.55;
        }

        .section-badge {
          border: 1px solid var(--line-strong);
          border-radius: 999px;
          color: var(--accent-ink);
          background: rgba(255, 255, 255, 0.74);
          padding: 0.5rem 0.75rem;
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 0.72rem;
          font-weight: 700;
        }

        .empty-panel {
          border: 1px dashed rgba(40, 85, 113, 0.34);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.68);
          padding: 1.35rem;
          color: var(--muted);
        }

        .empty-panel strong {
          display: block;
          margin-bottom: 0.22rem;
          color: var(--text);
          font-size: 1rem;
        }

        .stTabs [data-baseweb="tab-list"] {
          width: fit-content !important;
          max-width: 100% !important;
          margin: 0 auto 1.15rem auto !important;
          justify-content: center !important;
          gap: 6px !important;
          padding: 8px !important;
          border: 1px solid var(--line) !important;
          border-radius: 999px !important;
          background: rgba(255, 255, 255, 0.76) !important;
          box-shadow: var(--shadow-tight);
          backdrop-filter: blur(12px) saturate(112%);
          -webkit-backdrop-filter: blur(12px) saturate(112%);
        }

        button[data-baseweb="tab"] {
          border: 0 !important;
          border-radius: 999px !important;
          color: var(--muted) !important;
          font-weight: 720 !important;
          box-shadow: none !important;
          transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1), background-color 180ms ease, color 180ms ease;
        }

        button[data-baseweb="tab"]:active {
          transform: scale(0.98);
        }

        button[data-baseweb="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] * {
          background: var(--accent) !important;
          color: #ffffff !important;
        }

        [data-baseweb="tab-highlight"] {
          display: none !important;
        }

        [data-testid="stExpander"] {
          border: 1px solid var(--line) !important;
          border-radius: 8px !important;
          background: rgba(255, 255, 255, 0.88) !important;
          box-shadow: var(--shadow-tight);
        }

        .stTextInput input,
        .stNumberInput input,
        .stTextArea textarea,
        .stSelectbox div[data-baseweb="select"] {
          border-radius: 8px !important;
          border-color: var(--line) !important;
          background: rgba(255, 255, 255, 0.94) !important;
        }

        .stTextInput input:focus,
        .stNumberInput input:focus,
        .stTextArea textarea:focus {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 3px rgba(40, 85, 113, 0.12) !important;
        }

        .stButton button,
        .stDownloadButton button,
        .stLinkButton a {
          border-radius: 8px !important;
          border: 1px solid var(--line) !important;
          font-weight: 720 !important;
          transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1), border-color 180ms ease, background-color 180ms ease;
        }

        .stButton button:active,
        .stDownloadButton button:active,
        .stLinkButton a:active {
          transform: scale(0.98);
        }

        .stButton button[kind="primary"] {
          background: var(--accent) !important;
          color: #ffffff !important;
          border-color: var(--accent) !important;
        }

        [data-testid="stDataFrame"] {
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
          box-shadow: var(--shadow-tight);
        }

        .stAlert {
          border-radius: 8px !important;
        }

        @keyframes rise {
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }

        @keyframes breath {
          0%, 100% {
            transform: scale(1);
          }
          50% {
            transform: scale(0.78);
          }
        }

        @media (max-width: 980px) {
          .app-hero,
          .section-intro {
            grid-template-columns: 1fr;
          }

          .hero-title {
            max-width: 14ch;
          }

          .metric-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 620px) {
          .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
          }

          .hero-copy {
            padding: 1.3rem;
          }

          .hero-panel {
            min-height: 300px;
          }

          .metric-strip {
            grid-template-columns: 1fr;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    st.markdown(
        """
        <div class="app-hero">
          <section class="hero-copy">
            <div class="hero-kicker">Private extraction console</div>
            <div class="hero-title">Contract Extractor v2</div>
            <p class="hero-subtitle">
              Read PDFs from a controlled Google Drive folder, turn them into reviewable BoQ drafts,
              and approve clean records into Supabase without calling OpenAI APIs.
            </p>
          </section>
          <aside class="hero-panel" aria-label="Processing workflow">
            <div class="flow-rail">
              <div class="flow-step" style="--step: 1">
                <div class="flow-node">01</div>
                <div><div class="flow-label">Drive sync</div><div class="flow-meta">Private folder, service account</div></div>
              </div>
              <div class="flow-step" style="--step: 2">
                <div class="flow-node">02</div>
                <div><div class="flow-label">PaddleOCR fallback</div><div class="flow-meta">Only for pages without text layer</div></div>
              </div>
              <div class="flow-step" style="--step: 3">
                <div class="flow-node">03</div>
                <div><div class="flow-label">Human review</div><div class="flow-meta">Editable metadata and BoQ rows</div></div>
              </div>
              <div class="flow-step" style="--step: 4">
                <div class="flow-node">04</div>
                <div><div class="flow-label">Supabase final</div><div class="flow-meta">Existing approval RPC</div></div>
              </div>
            </div>
          </aside>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_strip(items: list[tuple[str, str]]) -> None:
    cells = "\n".join(
        f"""
        <div class="metric-box">
          <div class="metric-label">{escape(label)}</div>
          <div class="metric-value">{escape(value)}</div>
        </div>
        """
        for label, value in items
    )
    st.markdown(f'<div class="metric-strip">{cells}</div>', unsafe_allow_html=True)


def section_intro(title: str, body: str, badge: str | None = None) -> None:
    badge_html = f'<div class="section-badge">{escape(badge)}</div>' if badge else ""
    st.markdown(
        f"""
        <div class="section-intro">
          <div>
            <h2>{escape(title)}</h2>
            <p>{escape(body)}</p>
          </div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_panel(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="empty-panel">
          <strong>{escape(title)}</strong>
          <span>{escape(body)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
