import streamlit as st

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap');

:root {
    --rhino-ink: #071826;
    --rhino-slate: #2b4a5f;
    --rhino-signal: #f4511e;
    --rhino-mist: #e8eef2;
    --rhino-paper: #f9faf7;
    --rhino-line: #c7d3db;
}

.stApp {
    background:
        radial-gradient(circle at 84% 8%, rgba(52, 123, 145, 0.14), transparent 28rem),
        linear-gradient(180deg, #f9faf7 0%, #f3f6f7 100%);
    color: var(--rhino-ink);
    font-family: "Manrope", sans-serif;
}

.block-container {
    padding-top: 3.8rem;
}

[data-testid="stSidebar"] {
    background: var(--rhino-ink);
    border-right: 1px solid #183448;
}

[data-testid="stSidebar"] * {
    color: #eff5f7;
}

[data-testid="stSidebar"] [role="radiogroup"] label {
    border-radius: 0.6rem;
    padding: 0.45rem 0.7rem;
}

[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: rgba(244, 81, 30, 0.18);
}

h1, h2, h3 {
    color: var(--rhino-ink);
    font-family: "Barlow Condensed", sans-serif;
    letter-spacing: -0.02em;
}

h1 {
    font-size: clamp(3rem, 6vw, 5.2rem) !important;
    font-weight: 800 !important;
    line-height: 0.92 !important;
    margin-bottom: 0.9rem !important;
    text-transform: uppercase;
}

h2 {
    font-size: 2.2rem !important;
    font-weight: 700 !important;
}

h3 {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
}

code, .evidence-badge, .rhino-kicker, .rhino-meta {
    font-family: "IBM Plex Mono", monospace;
}

.rhino-wordmark {
    color: #f9faf7;
    font-family: "Barlow Condensed", sans-serif;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1;
    margin: 0.4rem 0 0.15rem;
    text-transform: uppercase;
}

.rhino-wordmark span {
    color: var(--rhino-signal);
}

.rhino-kicker {
    color: var(--rhino-signal);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.13em;
    margin-bottom: 0.7rem;
    text-transform: uppercase;
}

.rhino-deck {
    color: var(--rhino-slate);
    font-size: 1.05rem;
    line-height: 1.65;
    max-width: 44rem;
}

.rhino-status {
    border-left: 3px solid var(--rhino-signal);
    color: #b9c9d1;
    font-size: 0.78rem;
    line-height: 1.5;
    margin-top: 2rem;
    padding-left: 0.75rem;
}

.trace-card {
    background: rgba(255, 255, 255, 0.76);
    border: 1px solid var(--rhino-line);
    border-left: 4px solid var(--rhino-signal);
    border-radius: 0.45rem 1.2rem 1.2rem 0.45rem;
    box-shadow: 0 0.5rem 2.2rem rgba(7, 24, 38, 0.05);
    margin: 0.6rem 0;
    padding: 1rem 1.1rem;
}

.trace-card p {
    margin: 0.35rem 0;
}

.evidence-badge {
    background: var(--rhino-ink);
    border-radius: 999px;
    color: #f9faf7;
    display: inline-block;
    font-size: 0.68rem;
    margin: 0.15rem 0.15rem 0 0;
    padding: 0.22rem 0.5rem;
}

.rhino-meta {
    color: #5b7280;
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid var(--rhino-line);
    border-radius: 0.9rem;
    padding: 0.9rem 1rem;
}

[data-testid="stMetricValue"] {
    color: var(--rhino-ink);
    font-family: "Barlow Condensed", sans-serif;
    font-size: 2.4rem;
    font-weight: 700;
}

.stButton > button[kind="primary"],
.stDownloadButton > button {
    background: var(--rhino-signal);
    border: 1px solid var(--rhino-signal);
    border-radius: 0.55rem;
    color: white;
    font-weight: 700;
}

.stButton > button[kind="primary"]:hover,
.stDownloadButton > button:hover {
    background: #d94016;
    border-color: #d94016;
}

input:focus, textarea:focus, button:focus-visible, [tabindex]:focus-visible {
    outline: 3px solid rgba(244, 81, 30, 0.28) !important;
    outline-offset: 2px;
}

@media (max-width: 720px) {
    h1 {
        font-size: 3.05rem !important;
        line-height: 0.96 !important;
    }
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
}

@media (prefers-reduced-motion: reduce) {
    * {
        scroll-behavior: auto !important;
        transition: none !important;
    }
}
</style>
"""


def apply_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
