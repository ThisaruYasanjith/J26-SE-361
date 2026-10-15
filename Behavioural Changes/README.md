# Behavioral Drift Detection in Same-Signature Java Methods

**Research Component:** Individual Research Project for Software Governance Platform (`J26-SE-361`)  
**Component Directory:** `Behavioural Changes`

---

## 📌 Problem Overview

When software engineers modify an existing Java method without altering its signature (i.e., method name, parameter types, return type, and access modifiers remain identical), the Java compiler generates no warnings or syntax errors.

However, the **runtime behavior** may quietly diverge:
- Return value computation changes (e.g., shifted boundary conditions, altered discount formulas).
- Implicit preconditions tighten (e.g., throwing unexpected exceptions on previously valid inputs).
- Unannounced state mutations or side-effects are introduced (e.g., modifying caller-passed collections, new I/O).
- Exception contracts are violated (e.g., unchecked exceptions replace safe fallback values).

This phenomenon—**Same-Signature Behavioral Drift**—is a major source of silent software regressions and architectural degradation in evolving codebases.

---

## 🏗️ Architecture & Pipeline Flow

The prototype is organized into a modular 8-stage pipeline:

```
┌─────────────────────────┐
│    Java Method Input    │ (Raw Java method code v1 vs v2)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Same-Signature Verifier │ (Verifies exact method signature equivalence)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  LLM Semantic Analyzer  │ (High-throughput Code LLM via Groq Cloud)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Behavioral Fingerprint  │ (Pre/post-conditions, mutations, side-effects, exceptions)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Behavioral Drift Engine │ (Quantifies multi-dimensional drift score & severity)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Impact Assessment    │ (Blast radius, backward compatibility, systemic risk)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│     LLM Explanation     │ (Developer narrative, failure scenarios, JUnit tests)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│   UI Feedback / Streamlit│ (Interactive visual dashboard)
└─────────────────────────┘
```

---

## 📁 Project Structure & File Purpose

```
Behavioural Changes/
├── src/
│   ├── __init__.py           # Package marker
│   ├── method_parser.py      # Stage 1: Java AST & regex parsing into structured models
│   ├── signature_checker.py  # Stage 2: Verification of same-signature equivalence
│   ├── llm_analyzer.py       # Stages 3 & 4: Groq Cloud LLM semantic analysis & fingerprinting
│   ├── drift_engine.py       # Stage 5: Multi-dimensional drift quantification and scoring
│   ├── impact_assessor.py    # Stage 6: Blast radius, backward compatibility & architectural risk
│   └── explanation.py        # Stage 7: Groq-generated developer narrative & JUnit test generation
├── tests/
│   ├── __init__.py           # Test package marker
│   └── test_pipeline.py      # Unit tests for parser, signature checker, drift engine, impact assessor
├── app.py                    # Stage 8: Streamlit web dashboard for interactive demonstration
├── requirements.txt          # Python library dependencies
├── .env.example              # Template for Groq API key and model configuration
└── README.md                 # Component documentation
```

### Module Responsibilities:

1. **`src/method_parser.py` (Java Method Input & Parsing)**:
   - Parses raw Java method snippets, annotations, generics, and class-wrapped declarations.
   - Extracts method name, return type, parameters (types and names), modifiers, exceptions, and body.
   - Outputs a typed `JavaMethod` object model.

2. **`src/signature_checker.py` (Same-Signature Verification)**:
   - Compares the signatures of baseline (v1) and modified (v2) methods.
   - Verifies whether method name, return type, and ordered parameter types are identical with nested type canonicalization.
   - Halts drift analysis if signatures differ, flagging it as an explicit API contract change.

3. **`src/llm_analyzer.py` (LLM Semantic Analyzer & Fingerprinting)**:
   - Connects to Groq Cloud API running state-of-the-art open models (e.g., `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`).
   - Extracts structured behavioral fingerprints in strict JSON: preconditions, postconditions, state mutations, side-effects, exceptions, and return logic.

4. **`src/drift_engine.py` (Behavioral Drift Engine)**:
   - Compares baseline vs modified behavioral fingerprints across 6 weighted dimensions.
   - Computes a normalized drift score ($0.0 \le score \le 1.0$) and categorizes severity (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

5. **`src/impact_assessor.py` (Impact Assessment)**:
   - Analyzes caller blast radius (`LOCAL_METHOD`, `PACKAGE_PRIVATE`, `CROSS_MODULE`) based on access modifiers.
   - Evaluates backward compatibility and silent regression potential.
   - Emits architectural risk warnings and mitigation recommendations.

6. **`src/explanation.py` (LLM Explanation)**:
   - Queries Groq Cloud LLM to synthesize a human-readable developer narrative explaining *why* behavior drifted despite an identical signature.
   - Highlights concrete divergent runtime scenarios and suggests JUnit regression tests.

7. **`app.py` (UI Feedback)**:
   - Interactive Streamlit dashboard allowing users to input Java methods, select preset demonstration scenarios, and visualize the full 7-stage pipeline results powered by Groq.

---

## 🚀 Setup & Getting Started

### 1. Prerequisites
- **Python**: Version 3.10+
- **Groq API Key**: Obtain a free API key from [Groq Console](https://console.groq.com/)

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Configure your Groq API key:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
REQUEST_TIMEOUT_SECONDS=60
TEMPERATURE=0.1
```

### 3. Install Dependencies
```bash
py -m pip install -r requirements.txt
```

### 4. Run Unit Tests
```bash
py -m pytest -v
```

### 5. Launch Demonstration UI
```bash
py -m streamlit run app.py
```
