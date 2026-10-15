"""
Behavioral Drift Detection in Same-Signature Java Methods
Streamlit Demonstration Dashboard

Stage: UI Feedback
Integrates the full research pipeline:
Java Method Input → Same-Signature Verification → LLM Semantic Analyzer (Groq Cloud) →
Behavioral Fingerprinting → Behavioral Drift Engine → Impact Assessment →
LLM Explanation (Groq Cloud) → UI Feedback
"""

import streamlit as st
import os
import json
from dotenv import load_dotenv

from src.method_parser import MethodParser, JavaMethod
from src.signature_checker import SignatureChecker, SignatureComparisonResult
from src.llm_analyzer import LLMSemanticAnalyzer, BehavioralFingerprint
from src.drift_engine import BehavioralDriftEngine, DriftReport, DriftSeverity
from src.impact_assessor import ImpactAssessor, ImpactAssessment, RiskLevel
from src.explanation import ExplanationGenerator, ExplanationReport

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Behavioral Drift Detector | Java Methods",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #4A90E2;
        margin-bottom: 12px;
    }
    .badge-critical { color: #fff; background-color: #d9534f; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-high { color: #fff; background-color: #f0ad4e; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-medium { color: #fff; background-color: #0275d8; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-low { color: #fff; background-color: #5cb85c; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-none { color: #fff; background-color: #6c757d; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Preset Test Cases for Demonstration
PRESET_CASES = {
    "Case 1: Silent Boundary Logic Drift": {
        "v1": """public double calculateDiscount(double price, int customerTier) {
    if (price <= 0) {
        return 0.0;
    }
    if (customerTier >= 3) {
        return price * 0.15;
    }
    return price * 0.05;
}""",
        "v2": """public double calculateDiscount(double price, int customerTier) {
    if (price <= 0) {
        return 0.0;
    }
    // Drift: Tier boundary silently shifted from >=3 to >3, cutting tier 3 discount
    if (customerTier > 3) {
        return price * 0.20;
    }
    return price * 0.02;
}"""
    },
    "Case 2: Silent Runtime Exception Injection": {
        "v1": """public String formatOrderReceipt(String orderId, double amount) {
    if (orderId == null) {
        return "N/A";
    }
    return String.format("Order #%s : $%.2f", orderId, amount);
}""",
        "v2": """public String formatOrderReceipt(String orderId, double amount) {
    // Drift: Throws IllegalArgumentException instead of returning 'N/A'
    if (orderId == null) {
        throw new IllegalArgumentException("orderId cannot be null");
    }
    return String.format("Order #%s : $%.2f", orderId, amount);
}"""
    },
    "Case 3: Unannounced Side-Effect & Mutation": {
        "v1": """public boolean validateAndStoreSession(String token, List<String> permissions) {
    if (token == null || token.isEmpty()) {
        return false;
    }
    return permissions.contains("ADMIN");
}""",
        "v2": """public boolean validateAndStoreSession(String token, List<String> permissions) {
    if (token == null || token.isEmpty()) {
        return false;
    }
    // Drift: Mutates the caller's input list directly and writes to external audit log
    permissions.add("AUDITED_SESSION");
    System.out.println("Session validated for token: " + token);
    return permissions.contains("ADMIN");
}"""
    },
    "Case 4: Negative Test (Mismatched Signature)": {
        "v1": """public double calculateFee(double baseAmount, int durationDays) {
    return baseAmount * 0.05 * durationDays;
}""",
        "v2": """public double calculateFee(double baseAmount, String durationTier) {
    return baseAmount * 0.08;
}"""
    }
}


def main():
    st.title("🔍 Behavioral Drift Detection in Same-Signature Java Methods")
    st.caption("Research Component | J26-SE-361 Code Governance Microservice | Powered by Groq Cloud")

    # Sidebar: Configuration & LLM Health
    with st.sidebar:
        st.header("⚡ Groq Cloud LLM")
        
        default_key = os.getenv("GROQ_API_KEY", "")
        groq_api_key = st.text_input(
            "Groq API Key",
            value=default_key,
            type="password",
            help="Groq API Key (loaded from .env if present)"
        )

        groq_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama-3.1-70b-versatile",
            "mixtral-8x7b-32768",
            "gemma2-9b-it"
        ]
        default_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        default_idx = groq_models.index(default_model) if default_model in groq_models else 0

        model_name = st.selectbox(
            "Groq Model",
            options=groq_models,
            index=default_idx,
            help="Recommended: llama-3.3-70b-versatile for code and reasoning"
        )

        timeout = st.slider("Request Timeout (sec)", min_value=10, max_value=180, value=60)
        temp = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.1, step=0.05)

        analyzer = LLMSemanticAnalyzer(
            api_key=groq_api_key,
            model_name=model_name,
            timeout_seconds=timeout,
            temperature=temp
        )

        st.markdown("---")
        st.subheader("Groq API Status")
        if st.button("Check Groq Connection"):
            with st.spinner("Connecting to Groq Cloud..."):
                status = analyzer.check_connection()
                if status.get("connected"):
                    st.success(f"Connected to Groq Cloud! Model `{model_name}` is available.")
                else:
                    st.error(f"Connection failed: {status.get('error')}")

        st.markdown("---")
        st.subheader("Load Preset Scenario")
        selected_preset = st.selectbox("Select Scenario", list(PRESET_CASES.keys()))
        preset_data = PRESET_CASES[selected_preset]

    # Main Area: Method Inputs
    st.subheader("1. Java Method Input")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 📄 Baseline Version (v1)")
        v1_code = st.text_area(
            "Baseline Java Method Code",
            value=preset_data["v1"],
            height=220,
            key="v1_input"
        )

    with col2:
        st.markdown("##### 📄 Modified Version (v2)")
        v2_code = st.text_area(
            "Modified Java Method Code",
            value=preset_data["v2"],
            height=220,
            key="v2_input"
        )

    run_btn = st.button("🚀 Run Behavioral Drift Analysis Pipeline", type="primary", use_container_width=True)

    if run_btn:
        pipeline_progress = st.status("Running Behavioral Drift Detection Pipeline via Groq Cloud...", expanded=True)

        # STAGE 1: Method Parsing
        pipeline_progress.write("Stage 1: Parsing Java Methods (AST & Signature Extraction)...")
        parser = MethodParser()
        v1_parsed = parser.parse(v1_code)
        v2_parsed = parser.parse(v2_code)

        # STAGE 2: Same-Signature Verification
        pipeline_progress.write("Stage 2: Verifying Same-Signature Equivalence...")
        checker = SignatureChecker()
        sig_result = checker.check(v1_parsed, v2_parsed)

        st.markdown("---")
        st.subheader("2. Same-Signature Verification Results")
        if sig_result.is_same_signature:
            st.success(f"✅ **Same-Signature Verified!** Both methods share signature: `{v1_parsed.signature_str}`")
        else:
            st.error(f"❌ **Signature Mismatch Detected!** {sig_result.summary}")
            for m in sig_result.mismatches:
                st.warning(f"- **{m.component}**: Baseline `{m.baseline_value}` vs Modified `{m.modified_value}` ({m.description})")
            st.info("ℹ️ Behavioral Drift Detection applies to methods with identical signatures. This change constitutes an explicit API signature change.")
            pipeline_progress.update(label="Analysis Halted: Signature Mismatch", state="error")
            return

        # STAGE 3 & 4: LLM Semantic Analysis & Behavioral Fingerprinting
        pipeline_progress.write(f"Stage 3 & 4: Extracting Semantic Fingerprints via Groq (`{model_name}`)...")
        try:
            with st.spinner("Extracting behavioral fingerprints via Groq Cloud..."):
                fp1 = analyzer.extract_fingerprint(v1_parsed)
                fp2 = analyzer.extract_fingerprint(v2_parsed)
        except Exception as e:
            pipeline_progress.update(label="Groq Analysis Failed", state="error")
            st.error(f"Failed to extract fingerprints from Groq: {e}")
            st.warning("Please verify your Groq API key in the sidebar or in the `.env` file.")
            return

        st.markdown("---")
        st.subheader("3. Behavioral Fingerprint Comparison")
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            st.markdown("##### 🧬 Baseline Fingerprint (v1)")
            st.json({
                "Preconditions": fp1.preconditions,
                "Postconditions": fp1.postconditions,
                "State Mutations": fp1.state_mutations,
                "Side Effects": fp1.side_effects,
                "Exceptions Thrown": fp1.exceptions_thrown,
                "Return Behavior": fp1.return_behavior
            })

        with f_col2:
            st.markdown("##### 🧬 Modified Fingerprint (v2)")
            st.json({
                "Preconditions": fp2.preconditions,
                "Postconditions": fp2.postconditions,
                "State Mutations": fp2.state_mutations,
                "Side Effects": fp2.side_effects,
                "Exceptions Thrown": fp2.exceptions_thrown,
                "Return Behavior": fp2.return_behavior
            })

        # STAGE 5: Behavioral Drift Engine
        pipeline_progress.write("Stage 5: Computing Behavioral Drift Metrics...")
        drift_engine = BehavioralDriftEngine()
        drift_report = drift_engine.analyze(fp1, fp2)

        st.markdown("---")
        st.subheader("4. Behavioral Drift Metrics")
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.metric("Drift Score", f"{drift_report.drift_score * 100:.1f}%")
        with m_col2:
            st.metric("Drift Severity", drift_report.severity.value)
        with m_col3:
            st.metric("Drift Detected", "YES" if drift_report.drift_detected else "NO")

        st.markdown(f"**Summary:** {drift_report.summary}")
        if drift_report.flagged_drift_areas:
            st.write("**Affected Behavioral Dimensions:**", ", ".join(drift_report.flagged_drift_areas))

        with st.expander("Detailed Dimension Deltas"):
            for delta in drift_report.dimension_deltas:
                status_icon = "⚠️" if delta.has_drift else "✔️"
                st.markdown(f"{status_icon} **{delta.dimension.upper()}** (weight: {delta.weight:.2f})")
                if delta.has_drift:
                    if delta.added_behaviors:
                        st.markdown(f"- *Added in v2:* `{', '.join(delta.added_behaviors)}`")
                    if delta.removed_behaviors:
                        st.markdown(f"- *Removed from v1:* `{', '.join(delta.removed_behaviors)}`")
                else:
                    st.caption("No divergence detected in this dimension.")

        # STAGE 6: Impact Assessment
        pipeline_progress.write("Stage 6: Evaluating Architectural Impact & Blast Radius...")
        assessor = ImpactAssessor()
        vis_mod = " ".join(v1_parsed.modifiers)
        impact = assessor.assess(sig_result, drift_report, visibility_modifier=vis_mod)

        st.markdown("---")
        st.subheader("5. Impact & Architectural Blast Radius Assessment")
        i_col1, i_col2, i_col3 = st.columns(3)
        with i_col1:
            st.metric("Systemic Risk Level", impact.risk_level.value)
        with i_col2:
            st.metric("Blast Radius Scope", impact.blast_radius.value)
        with i_col3:
            st.metric("Backward Compatibility", "INTACT" if impact.backward_compatibility_intact else "COMPROMISED")

        st.markdown(f"**Executive Impact Assessment:** {impact.executive_summary}")
        st.markdown(f"**Silent Bug Vulnerability:** {impact.silent_regression_risk}")

        if impact.architectural_risks:
            st.markdown("##### 🚨 Architectural Risks:")
            for r in impact.architectural_risks:
                st.markdown(f"- {r}")

        if impact.recommended_mitigations:
            st.markdown("##### 🛡️ Recommended Mitigations:")
            for m in impact.recommended_mitigations:
                st.markdown(f"- {m}")

        # STAGE 7: LLM Explanation
        pipeline_progress.write(f"Stage 7: Generating Technical Narrative & Test Recommendations via Groq (`{model_name}`)...")
        explainer = ExplanationGenerator(
            api_key=groq_api_key,
            model_name=model_name,
            timeout_seconds=timeout,
            temperature=temp
        )
        try:
            with st.spinner("Synthesizing developer explanation via Groq Cloud..."):
                explanation = explainer.generate_explanation(v1_parsed, v2_parsed, sig_result, drift_report, impact)
        except Exception as e:
            st.warning(f"Could not generate deep LLM explanation: {e}")
            explanation = None

        st.markdown("---")
        st.subheader("6. LLM Behavioral Explanation & Developer Guidance")
        if explanation:
            st.info(f"**Overview:** {explanation.overview}")
            st.markdown("##### 🔬 Deep Technical Breakdown")
            st.write(explanation.detailed_drift_breakdown)

            if explanation.failure_scenarios:
                st.markdown("##### ⚡ Divergent Runtime Scenarios (Failure Modes):")
                for s in explanation.failure_scenarios:
                    st.markdown(f"- {s}")

            if explanation.recommended_unit_tests:
                st.markdown("##### 🧪 Suggested JUnit Tests to Detect Drift:")
                for t in explanation.recommended_unit_tests:
                    st.code(t, language="java")

            st.markdown("##### 💡 Developer Guidance:")
            st.write(explanation.developer_guidance)

        pipeline_progress.update(label="Behavioral Drift Analysis Complete!", state="complete")


if __name__ == "__main__":
    main()
