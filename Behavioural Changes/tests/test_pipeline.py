"""
Unit tests for the Behavioral Drift Detection pipeline components.
"""

import pytest
from src.method_parser import MethodParser, JavaMethod, MethodParameter
from src.signature_checker import SignatureChecker
from src.llm_analyzer import BehavioralFingerprint
from src.drift_engine import BehavioralDriftEngine, DriftSeverity
from src.impact_assessor import ImpactAssessor, RiskLevel, BlastRadius


def test_method_parser_snippet():
    code = """
    public double calculateDiscount(double price, int customerTier) {
        if (price < 0) {
            throw new IllegalArgumentException("Negative price");
        }
        return price * 0.10;
    }
    """
    parser = MethodParser()
    method = parser.parse(code)

    assert method.name == "calculateDiscount"
    assert method.return_type == "double"
    assert len(method.parameters) == 2
    assert method.parameters[0].type == "double"
    assert method.parameters[0].name == "price"
    assert method.parameters[1].type == "int"
    assert method.parameters[1].name == "customerTier"
    assert "public" in method.modifiers


def test_method_parser_with_annotations_and_generics():
    code = """
    @Override
    @Deprecated
    public List<String> processEntities(Map<String, Integer> mapping, String... tags) throws IOException, SQLException {
        return new ArrayList<>();
    }
    """
    parser = MethodParser()
    method = parser.parse(code)

    assert method.name == "processEntities"
    assert "List<String>" in method.return_type
    assert len(method.parameters) == 2
    assert "Map<String, Integer>" in method.parameters[0].type
    assert "tags" in method.parameters[1].name
    assert "@Override" in method.annotations
    assert "IOException" in method.thrown_exceptions


def test_same_signature_checker_positive():
    v1_code = """
    public double calculateDiscount(double price, int customerTier) {
        return price * 0.10;
    }
    """
    v2_code = """
    public double calculateDiscount(double price, int customerTier) {
        if (customerTier > 3) {
            return price * 0.25;
        }
        return price * 0.05;
    }
    """
    parser = MethodParser()
    checker = SignatureChecker()

    v1 = parser.parse(v1_code)
    v2 = parser.parse(v2_code)
    res = checker.check(v1, v2)

    assert res.is_same_signature is True
    assert len(res.mismatches) == 0
    assert res.allows_drift_analysis is True


def test_same_signature_checker_type_normalization():
    v1_code = "public List<java.lang.String> fetchNames(java.lang.String query) { return null; }"
    v2_code = "public List<String> fetchNames(String query) { return null; }"

    parser = MethodParser()
    checker = SignatureChecker()

    v1 = parser.parse(v1_code)
    v2 = parser.parse(v2_code)
    res = checker.check(v1, v2)

    assert res.is_same_signature is True


def test_same_signature_checker_negative():
    v1_code = "public double calculateDiscount(double price, int customerTier) { return 0.0; }"
    v2_code = "public double calculateDiscount(double price, String tierName) { return 0.0; }"

    parser = MethodParser()
    checker = SignatureChecker()

    v1 = parser.parse(v1_code)
    v2 = parser.parse(v2_code)
    res = checker.check(v1, v2)

    assert res.is_same_signature is False
    assert len(res.mismatches) > 0


def test_drift_engine_identical_fingerprints():
    fp = BehavioralFingerprint(
        method_name="processPayment",
        preconditions=["amount > 0"],
        postconditions=["balance reduced by amount"],
        state_mutations=["balance"],
        side_effects=["log transaction"],
        exceptions_thrown=["IllegalArgumentException"],
        return_behavior="returns boolean confirmation"
    )

    engine = BehavioralDriftEngine()
    report = engine.analyze(fp, fp)

    assert report.drift_detected is False
    assert report.drift_score == 0.0
    assert report.severity == DriftSeverity.NONE


def test_drift_engine_divergent_fingerprints():
    fp1 = BehavioralFingerprint(
        method_name="calculateTax",
        preconditions=["income >= 0"],
        postconditions=["tax is 15% of income"],
        state_mutations=[],
        side_effects=[],
        exceptions_thrown=[],
        return_behavior="15% flat tax"
    )

    fp2 = BehavioralFingerprint(
        method_name="calculateTax",
        preconditions=["income >= 0", "residence != null"],
        postconditions=["progressive tax rate bracket applied"],
        state_mutations=[],
        side_effects=["audit log sent to compliance server"],
        exceptions_thrown=["TaxJurisdictionException"],
        return_behavior="bracket-based tax calculation"
    )

    engine = BehavioralDriftEngine()
    report = engine.analyze(fp1, fp2)

    assert report.drift_detected is True
    assert report.drift_score > 0.4
    assert len(report.flagged_drift_areas) >= 3


def test_impact_assessor():
    parser = MethodParser()
    checker = SignatureChecker()
    engine = BehavioralDriftEngine()
    assessor = ImpactAssessor()

    v1 = parser.parse("public double calculate(double val) { return val * 2; }")
    v2 = parser.parse("public double calculate(double val) { if (val < 0) throw new RuntimeException(); return val * 2; }")

    fp1 = BehavioralFingerprint(
        method_name="calculate",
        preconditions=[],
        postconditions=["returns double"],
        exceptions_thrown=[],
        return_behavior="multiplies by 2"
    )
    fp2 = BehavioralFingerprint(
        method_name="calculate",
        preconditions=["val >= 0"],
        postconditions=["returns double"],
        exceptions_thrown=["RuntimeException when val < 0"],
        return_behavior="multiplies by 2"
    )

    sig_res = checker.check(v1, v2)
    drift = engine.analyze(fp1, fp2)
    impact = assessor.assess(sig_res, drift, visibility_modifier="public")

    assert impact.blast_radius == BlastRadius.CROSS_MODULE
    assert impact.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert len(impact.architectural_risks) > 0
    assert len(impact.recommended_mitigations) > 0


def test_groq_llm_analyzer_json_parsing():
    from src.llm_analyzer import LLMSemanticAnalyzer

    analyzer = LLMSemanticAnalyzer(api_key="mock_key")
    raw_json = """
    ```json
    {
        "preconditions": ["price > 0"],
        "postconditions": ["returns discounted price"],
        "state_mutations": [],
        "side_effects": [],
        "exceptions_thrown": ["IllegalArgumentException"],
        "return_behavior": "calculates percentage discount",
        "invariants_and_assumptions": []
    }
    ```
    """
    fp = analyzer._parse_llm_json_response("calculateDiscount", raw_json)

    assert fp.method_name == "calculateDiscount"
    assert "price > 0" in fp.preconditions
    assert "returns discounted price" in fp.postconditions
    assert "IllegalArgumentException" in fp.exceptions_thrown
    assert fp.return_behavior == "calculates percentage discount"


def test_groq_explanation_json_parsing():
    from src.explanation import ExplanationGenerator
    from src.drift_engine import BehavioralDriftEngine, DriftSeverity
    from src.impact_assessor import ImpactAssessor

    explainer = ExplanationGenerator(api_key="mock_key")
    fp = BehavioralFingerprint(
        method_name="testMethod",
        preconditions=[],
        postconditions=[],
        return_behavior="nominal"
    )
    drift = BehavioralDriftEngine().analyze(fp, fp)
    from src.signature_checker import SignatureComparisonResult
    sig_res = SignatureComparisonResult(
        is_same_signature=True,
        method_name="testMethod",
        summary="Identical"
    )
    impact = ImpactAssessor().assess(sig_res, drift)

    raw_json = """
    {
        "overview": "Logic changed slightly.",
        "detailed_drift_breakdown": "Boundary shifted from 3 to 4.",
        "failure_scenarios": ["Input 3 fails."],
        "recommended_unit_tests": ["assertEquals(0.15, calc(100, 3));"],
        "developer_guidance": "Check downstream callers."
    }
    """
    report = explainer._parse_explanation_response(raw_json, drift, impact)

    assert report.overview == "Logic changed slightly."
    assert len(report.failure_scenarios) == 1
    assert "Input 3 fails." in report.failure_scenarios[0]
    assert len(report.recommended_unit_tests) == 1

