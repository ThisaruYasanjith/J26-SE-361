"""
Behavioral Drift Detection in Same-Signature Java Methods
Streamlit Demonstration Dashboard

Stage: UI Feedback & Governance Pipeline
Integrates the complete local research pipeline:
Java Method Input → Same-Signature Verification → Local CodeT5 Inference (Salesforce/codet5-small) →
Behavioral Category Analysis → Behavioral Drift Engine → Impact Assessment →
Developer Explanation & JUnit Generation → UI Feedback
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
    page_title="Behavioral Drift Detector | Fine-Tuned CodeT5",
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
    .cat-badge {
        display: inline-block;
        background-color: #2b3a4a;
        color: #61dafb;
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 6px;
        margin-bottom: 4px;
        font-family: monospace;
        font-size: 12px;
        font-weight: 600;
        border: 1px solid #3d5166;
    }
    .cat-added {
        background-color: #1e3a2f;
        color: #4ade80;
        border-color: #2e6047;
    }
    .cat-removed {
        background-color: #3d1f24;
        color: #f87171;
        border-color: #652b32;
    }
    .cat-retained {
        background-color: #1e293b;
        color: #94a3b8;
        border-color: #334155;
    }
</style>
""", unsafe_allow_html=True)

# Preset Test Cases for Demonstration
PRESET_CASES = {
    "Dataset Example 001: File Copy -> DB Status & Delete": {
        "v1": """public Object buildInventoryItemSummary(InventoryItem item, Long itemId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    java.nio.file.Files.copy(path, backupPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    return "INVENTORYITEM-" + itemId;
}""",
        "v2": """public Object buildInventoryItemSummary(InventoryItem item, Long itemId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    inventoryRepository.updateStatus(itemId, "PENDING");
    java.nio.file.Files.deleteIfExists(path);
    return String.valueOf(itemId);
}"""
    },
    "Dataset Example 003: Account Read -> File Write Added": {
        "v1": """public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    accountRepository.findById(accountId);
}""",
        "v2": """public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    java.nio.file.Files.writeString(path, message);
    accountRepository.findById(accountId);
}"""
    },
    "Dataset Example 004: Validation & Exception Behavior Added": {
        "v1": """public void checkMessageRecordRequest(MessageRecord messageRecord, Long messageId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    logger.trace("MessageRecord operation started");
    double averageAmount = amount / Math.max(quantity, 1);
}""",
        "v2": """public void checkMessageRecordRequest(MessageRecord messageRecord, Long messageId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {
    logger.trace("MessageRecord operation started");
    double averageAmount = amount / Math.max(quantity, 1);
    if (messageId == null) {
        throw new IllegalArgumentException("identifier is required");
    }
}"""
    },
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


def render_badges(categories, badge_class="cat-badge"):
    if not categories:
        return "<em>None detected</em>"
    return " ".join([f'<span class="{badge_class}">{c}</span>' for c in categories])


def main():
    st.title("🔍 Behavioral Drift Detection in Same-Signature Java Methods")
    st.caption("Local AI Pipeline | Powered by Fine-Tuned CodeT5 (`Salesforce/codet5-small`) | J26-SE-361 Code Governance")

    # Sidebar: Local Model Configuration & Health
    with st.sidebar:
        st.header("⚡ Local CodeT5 Service")
        st.info("Operating entirely offline on local hardware. No Groq API key or external cloud APIs required.")

        default_service_url = os.getenv("CODET5_SERVICE_URL", "http://localhost:8000")
        service_url = st.text_input(
            "Service URL",
            value=default_service_url,
            help="URL where 'inference_service.py' is running (default: http://localhost:8000)"
        )

        timeout = st.slider("Request Timeout (sec)", min_value=10, max_value=180, value=60)

        analyzer = LLMSemanticAnalyzer(
            service_url=service_url,
            timeout_seconds=timeout
        )

        st.markdown("---")
        st.subheader("Model Service Health")
        if st.button("Check Service Connection"):
            with st.spinner(f"Connecting to {service_url}..."):
                status = analyzer.check_connection()
                if status.get("connected"):
                    st.success(f"Connected to Local CodeT5! Device: `{status.get('device')}`")
                    st.caption(f"Model Path: `{status.get('model_path')}`")
                else:
                    st.error(f"Connection failed: {status.get('error')}")
                    st.warning("To start the local inference service, run:\n`python inference_service.py`")

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
        pipeline_progress = st.status("Running Behavioral Drift Detection Pipeline via Local CodeT5...", expanded=True)

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

        # STAGE 3 & 4: Local CodeT5 Behavioral Classification
        pipeline_progress.write("Stage 3 & 4: Classifying Behavioral Categories via Fine-Tuned CodeT5...")
        try:
            with st.spinner("Executing local CodeT5 inference..."):
                fp1, fp2, comparison = analyzer.extract_pair_fingerprints(v1_parsed, v2_parsed)
        except Exception as e:
            pipeline_progress.update(label="Local CodeT5 Analysis Failed", state="error")
            st.error(f"Failed to query local CodeT5 service: {e}")
            st.warning("Please ensure the FastAPI service is running locally:\n`python inference_service.py`")
            return

        st.markdown("---")
        st.subheader("3. Fine-Tuned CodeT5 Behavioral Categories & Extracted Bodies")

        cat_col1, cat_col2 = st.columns(2)
        with cat_col1:
            st.markdown("##### 🏷️ Baseline Categories (v1)")
            st.markdown(render_badges(fp1.categories), unsafe_allow_html=True)
            with st.expander("Extracted Baseline Method Body"):
                st.code(fp1.method_body if fp1.method_body else "/* empty body */", language="java")

        with cat_col2:
            st.markdown("##### 🏷️ Modified Categories (v2)")
            st.markdown(render_badges(fp2.categories), unsafe_allow_html=True)
            with st.expander("Extracted Modified Method Body"):
                st.code(fp2.method_body if fp2.method_body else "/* empty body */", language="java")

        # Category Deltas
        st.markdown("##### 📊 Behavioral Category Changes (v1 → v2)")
        d_col1, d_col2, d_col3 = st.columns(3)
        with d_col1:
            added = comparison.get("added_categories", [])
            st.markdown(f"**➕ Added in v2 ({len(added)}):**")
            st.markdown(render_badges(added, "cat-badge cat-added"), unsafe_allow_html=True)
        with d_col2:
            removed = comparison.get("removed_categories", [])
            st.markdown(f"**➖ Removed from v1 ({len(removed)}):**")
            st.markdown(render_badges(removed, "cat-badge cat-removed"), unsafe_allow_html=True)
        with d_col3:
            retained = comparison.get("retained_categories", [])
            st.markdown(f"**🔁 Retained in Both ({len(retained)}):**")
            st.markdown(render_badges(retained, "cat-badge cat-retained"), unsafe_allow_html=True)

        # STAGE 5: Behavioral Drift Engine
        pipeline_progress.write("Stage 5: Computing Multi-Dimensional Behavioral Drift Metrics...")
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

        # STAGE 7: Developer Explanation & JUnit Tests
        pipeline_progress.write("Stage 7: Synthesizing Developer Explanation & JUnit Regression Tests...")
        explainer = ExplanationGenerator()
        explanation = explainer.generate_explanation(v1_parsed, v2_parsed, sig_result, drift_report, impact)

        st.markdown("---")
        st.subheader("6. Developer Guidance & Regression Test Generation")
        st.info(f"**Overview:** {explanation.overview}")
        st.markdown("##### 🔬 Technical Breakdown")
        st.write(explanation.detailed_drift_breakdown)

        if explanation.failure_scenarios:
            st.markdown("##### ⚡ Divergent Runtime Scenarios (Failure Modes):")
            for s in explanation.failure_scenarios:
                st.markdown(f"- {s}")

        if explanation.recommended_unit_tests:
            st.markdown("##### 🧪 Suggested JUnit Tests to Guard Against Drift:")
            for t in explanation.recommended_unit_tests:
                st.code(t, language="java")

        st.markdown("##### 💡 Developer Guidance:")
        st.write(explanation.developer_guidance)

        pipeline_progress.update(label="Behavioral Drift Analysis Complete!", state="complete")


if __name__ == "__main__":
    main()
