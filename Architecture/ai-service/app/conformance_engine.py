import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.conformance_models import (
    ArchitectureViolation, ConformanceResult, ConformanceRuleInfo, ConformanceSummary,
)
from app.custom_rule_store import CustomRuleStore
from app.models import ComponentInfo, ProjectContext
from app.rule_validator import RuleValidationSetupError, RuleValidator


class ConformanceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def package_matches(package: str, selector: str) -> bool:
    # A short package name is a whole segment; qualified names select a package subtree.
    if "." not in selector:
        return selector in package.split(".")
    return package == selector or package.startswith(selector + ".")


def _specificity(selector: dict) -> tuple[int, int]:
    kind = selector["entity_type"]
    if kind in {"COMPONENT", "CLASS", "INTERFACE"}:
        return (2, 0)
    return (1, len(selector["name"].split("."))) if kind == "PACKAGE" else (0, 0)


def _narrows(selector: dict, broader: dict, members: frozenset[str], broader_members: frozenset[str]) -> bool:
    if selector["entity_type"] in {"COMPONENT", "CLASS", "INTERFACE"}:
        return members <= broader_members
    if selector["entity_type"] != broader["entity_type"]:
        return False  # Package and Spring-layer categories can overlap without either containing the other.
    if selector["entity_type"] == "LAYER":
        return selector["name"] == broader["name"]
    if "." not in selector["name"]:
        return selector["name"] == broader["name"]
    return package_matches(selector["name"], broader["name"])


@dataclass(frozen=True, order=True)
class _Evidence:
    source: str
    relationship: str
    target: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    origin: str
    body: dict
    sources: frozenset[str]
    targets: frozenset[str]

    @property
    def exception(self) -> bool:
        return self.body["is_exception"] or self.body["rule_type"] == "EXCEPTION"

    @property
    def specificity(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return (_specificity(self.body["source"]), _specificity(self.body["target"]))


class _ProjectIndex:
    def __init__(self, context: ProjectContext) -> None:
        self.entities: dict[str, ComponentInfo] = {}
        self.simple_names: dict[str, set[str]] = defaultdict(set)
        self.layers: dict[str, set[str]] = defaultdict(set)
        self.packages: dict[str, set[str]] = defaultdict(set)
        for component in sorted(context.components, key=lambda item: item.name):
            if component.name in self.entities:
                raise ConformanceError(f"Duplicate project entity name {component.name}. Analyze and sync a unique entity graph.", 409)
            self.entities[component.name] = component
            self.layers[component.spring_type].add(component.name)
            self.packages[component.package].add(component.name)
        # External targets remain usable by exact COMPONENT name, but have no inferred class/layer metadata.
        self.names = set(self.entities) | {edge.target for edge in context.relationships if "." in edge.target}
        for name in self.names:
            self.simple_names[name.rsplit(".", 1)[-1]].add(name)
        evidence = set()
        for edge in context.relationships:
            source = self.resolve_name(edge.source)
            if source not in self.entities:
                continue  # Without an analyzed source there is no reliable file/location for a violation.
            target = self.resolve_name(edge.target)
            location = edge.source_location or self.entities[source].source_location
            evidence.add(_Evidence(source, edge.relationship, target, location.start_line, location.end_line))
        for component in self.entities.values():
            location = component.source_location
            evidence.add(_Evidence(component.name, "LOCATED_IN", component.package, location.start_line, location.end_line))
        self.evidence = sorted(evidence)
        self.by_relationship: dict[str, list[_Evidence]] = defaultdict(list)
        self.outgoing: dict[tuple[str, str], set[str]] = defaultdict(set)
        for item in self.evidence:
            self.by_relationship[item.relationship].append(item)
            self.outgoing[item.source, item.relationship].add(item.target)

    def resolve_name(self, name: str) -> str:
        if name in self.names or "." in name:
            return name
        matches = self.simple_names.get(name, set())
        if len(matches) > 1:
            raise ConformanceError(f"Ambiguous entity name {name}; use a qualified name. Matches: {', '.join(sorted(matches))}")
        return next(iter(matches)) if matches else name

    def select(self, selector: dict, *, placement: bool = False) -> frozenset[str]:
        kind, name = selector["entity_type"], selector["name"]
        if placement:
            if kind != "PACKAGE":
                raise ConformanceError("LOCATED_IN rules require a PACKAGE target.")
            return frozenset(package for package in self.packages if package_matches(package, name))
        if kind == "LAYER":
            if name not in {"CONTROLLER", "SERVICE", "REPOSITORY", "COMPONENT", "CONFIGURATION", "NONE"}:
                raise ConformanceError(f"Unknown Spring layer {name}; use an analyzer spring_type label.")
            return frozenset(self.layers.get(name, set()))
        if kind == "PACKAGE":
            return frozenset(entity for package, entities in self.packages.items()
                             if package_matches(package, name) for entity in entities)
        resolved = self.resolve_name(name)
        if kind == "COMPONENT":
            return frozenset([resolved]) if resolved in self.names else frozenset()
        entity = self.entities.get(resolved)
        return frozenset([resolved]) if entity is not None and entity.entity_type == kind else frozenset()


class ConformanceEngine:
    def __init__(self, base_rules_path: Path, custom_rules: CustomRuleStore) -> None:
        self.base_rules_path = Path(base_rules_path)
        self.custom_rules = custom_rules
        self.validator = RuleValidator()

    def _base_rules(self) -> list[dict]:
        try:
            entries = json.loads(self.base_rules_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConformanceError(f"Cannot read base architecture rules: {error}") from error
        if not isinstance(entries, list):
            raise ConformanceError("Base architecture rules must be a list of stored VALID rules.")
        for entry in entries:
            try:
                valid = self.validator.validate(entry).valid
            except RuleValidationSetupError as error:
                raise ConformanceError(str(error)) from error
            if not valid or entry.get("status") != "VALID" or not isinstance(entry.get("rule_id"), str) or not entry["rule_id"].strip():
                raise ConformanceError("Base architecture rules must contain schema-valid VALID entries with rule IDs.")
        return entries

    def check(self, context: ProjectContext) -> ConformanceResult:
        index = _ProjectIndex(context)
        entries = [(entry, "BASE") for entry in self._base_rules()]
        entries += [(entry, "CUSTOM") for entry in self.custom_rules.load_rules()]
        rules = []
        ids = set()
        for entry, origin in sorted(entries, key=lambda item: (item[0]["rule_id"], item[1])):
            rule_id, body = entry["rule_id"], entry["rule"]
            if rule_id in ids:
                raise ConformanceError(f"Stored architecture rules contain duplicate rule ID {rule_id}.")
            ids.add(rule_id)
            if body["rule_type"] == "PACKAGE_PLACEMENT" and body["relationship"] != "LOCATED_IN":
                raise ConformanceError(f"Package placement rule {rule_id} must use LOCATED_IN.")
            placement = body["relationship"] == "LOCATED_IN"
            rules.append(_Rule(rule_id, origin, body, index.select(body["source"]),
                               index.select(body["target"], placement=placement)))

        violations = []
        metadata = {}
        permissions = [rule for rule in rules if rule.body["action"] in {"ALLOW", "ONLY"}]
        for rule in rules:
            previous_count = len(violations)
            action, relationship = rule.body["action"], rule.body["relationship"]
            if action == "ALLOW":
                continue
            if action in {"DENY", "ONLY"}:
                for evidence in index.by_relationship[relationship]:
                    source_matches = evidence.source in rule.sources
                    if evidence.target not in rule.targets or (source_matches if action == "ONLY" else not source_matches):
                        continue
                    if not self._permitted(rule, evidence, permissions):
                        violations.append(self._violation(context, index, rule, evidence))
            else:  # REQUIRE is existential for each matching source, not an all-to-all dependency.
                for source in sorted(rule.sources & index.entities.keys()):
                    if index.outgoing[source, relationship] & rule.targets:
                        continue
                    entity = index.entities[source]
                    evidence = _Evidence(source, relationship, rule.body["target"]["name"],
                                         entity.source_location.start_line, entity.source_location.end_line)
                    if relationship == "LOCATED_IN":
                        actual = _Evidence(source, relationship, entity.package, evidence.start_line, evidence.end_line)
                        if self._permitted(rule, actual, permissions, alternative_package=True):
                            continue
                    violations.append(self._violation(context, index, rule, evidence))
            if len(violations) > previous_count:
                metadata[rule.rule_id] = ConformanceRuleInfo(rule_type=rule.body["rule_type"], rule_source=rule.origin)
        violations.sort(key=lambda item: (item.rule_id, item.source, item.target or "", item.relationship or "",
                                          item.file_path, item.start_line, item.end_line, item.violation_id))
        base_count = sum(metadata[item.rule_id].rule_source == "BASE" for item in violations)
        return ConformanceResult(project_name=context.project_name, conformant=not violations, violations=violations,
                                 summary=ConformanceSummary(total=len(violations), base_rule_violations=base_count,
                                                            custom_rule_violations=len(violations) - base_count),
                                 rule_metadata=metadata)

    @staticmethod
    def _permitted(restriction: _Rule, evidence: _Evidence, permissions: list[_Rule], *, alternative_package: bool = False) -> bool:
        for permission in permissions:
            if permission.rule_id == restriction.rule_id or permission.body["relationship"] != evidence.relationship:
                continue
            if evidence.source not in permission.sources or evidence.target not in permission.targets:
                continue
            if restriction.exception and not permission.exception:
                continue
            if not permission.exception and permission.origin != "CUSTOM":
                continue
            lower, higher = restriction.specificity, permission.specificity
            dominates = all(high >= low for high, low in zip(higher, lower))
            stricter = any(high > low for high, low in zip(higher, lower))
            # A permission must narrow both selector domains, except for ONLY's excluded-source domain
            # and an explicitly permitted alternative package for a placement requirement.
            if restriction.body["action"] == "ONLY":
                if {permission.body["source"]["entity_type"], restriction.body["source"]["entity_type"]} == {"PACKAGE", "LAYER"}:
                    continue
            elif not _narrows(permission.body["source"], restriction.body["source"], permission.sources, restriction.sources):
                continue
            if not alternative_package and not _narrows(permission.body["target"], restriction.body["target"],
                                                         permission.targets, restriction.targets):
                continue
            named_exception = permission.exception and any(part[0] == 2 for part in higher)
            if dominates and (stricter or (named_exception and not restriction.exception)):
                return True
        return False

    @staticmethod
    def _violation(context: ProjectContext, index: _ProjectIndex, rule: _Rule, evidence: _Evidence) -> ArchitectureViolation:
        entity = index.entities[evidence.source]
        target = evidence.target
        verb = {"DEPENDS_ON": "depend on", "CALLS": "call", "IMPORTS": "import", "EXTENDS": "extend",
                "IMPLEMENTS": "implement", "LOCATED_IN": "be located in"}[evidence.relationship]
        action = rule.body["action"]
        if action == "ONLY":
            allowed = rule.body["source"]["name"]
            message = f"Only {allowed} may {verb} {target}; {entity.name} currently does so."
            correction = f"Remove this relationship or route it through {allowed}."
        elif action == "REQUIRE":
            message = (f"{entity.name} must be located in a {target} package." if evidence.relationship == "LOCATED_IN"
                       else f"{entity.name} must {verb} {target}.")
            correction = f"Move {entity.name} to a {target} package." if evidence.relationship == "LOCATED_IN" else f"Add a {evidence.relationship} relationship from {entity.name} to a matching {target}."
        else:
            message = f"{entity.name} must not {verb} {target}."
            correction = f"Remove the {evidence.relationship} relationship or change the design to satisfy {rule.rule_id}."
        identity = [context.project_name, rule.origin, rule.rule_id, evidence.source, evidence.relationship,
                    target, entity.file_path, evidence.start_line, evidence.end_line]
        identifier = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
        prefix = f"{rule.origin} rule {rule.rule_id} ({rule.body['rule_type']}, {action})"
        if action == "ONLY":
            explanation = f"{prefix} restricts incoming {evidence.relationship} access to {rule.body['source']['name']}; {entity.name} is outside that selection."
        elif action == "REQUIRE":
            explanation = f"{prefix} requires a matching {evidence.relationship} condition for {entity.name}; none was recorded."
        else:
            explanation = f"{prefix} prohibits this {evidence.relationship} relationship, which was recorded at the reported source location."
        if action == "REQUIRE" and evidence.relationship == "LOCATED_IN":
            explanation += f" Actual package: {entity.package or '(default package)'}."
        return ArchitectureViolation(violation_id=f"VIOLATION_{identifier}", rule_id=rule.rule_id, severity="ERROR", message=message,
                                     source=evidence.source, target=target, relationship=evidence.relationship,
                                     file_path=entity.file_path, start_line=evidence.start_line, end_line=evidence.end_line,
                                     explanation=explanation, suggested_correction=correction)
