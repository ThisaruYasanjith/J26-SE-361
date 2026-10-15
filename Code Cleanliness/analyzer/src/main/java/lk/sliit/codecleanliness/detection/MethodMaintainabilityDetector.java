
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

import lk.sliit.codecleanliness.metrics.MethodMetrics;
import lk.sliit.codecleanliness.metrics.MethodMetricsCalculator;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class MethodMaintainabilityDetector {

    private final MethodMetricsCalculator calculator;

    public MethodMaintainabilityDetector() {
        this(new MethodMetricsCalculator());
    }

    public MethodMaintainabilityDetector(
            MethodMetricsCalculator calculator) {

        this.calculator = Objects.requireNonNull(calculator);
    }

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            MethodDetectionThresholds thresholds) {

        Objects.requireNonNull(repository);
        Objects.requireNonNull(thresholds);

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        // Process every successfully parsed Java file
        // in a deterministic order.
        List<Map.Entry<Path, CompilationUnit>> files =
                repository.parsedFiles()
                        .entrySet()
                        .stream()
                        .sorted(
                                Comparator.comparing(
                                        entry ->
                                                entry.getKey().toString()
                                )
                        )
                        .toList();

        for (Map.Entry<Path, CompilationUnit> entry : files) {

            Path file = entry.getKey()
                    .toAbsolutePath()
                    .normalize();

            CompilationUnit unit = entry.getValue();

            for (MethodDeclaration method :
                    unit.findAll(MethodDeclaration.class)) {

                // Methods without a body cannot be assessed
                // using implementation-level metrics.
                if (method.getBody().isEmpty()) {
                    continue;
                }

                // Source positions are necessary for
                // evidence-backed findings.
                if (method.getRange().isEmpty()) {
                    continue;
                }

                MethodMetrics metrics =
                        calculator.calculate(method);

                int startLine = method.getRange()
                        .orElseThrow()
                        .begin.line;

                int endLine = method.getRange()
                        .orElseThrow()
                        .end.line;

                // Build the declaring type's nested name.
                // Example: Outer.Helper.process()
                List<String> ownerParts = new ArrayList<>();

                Node current =
                        method.getParentNode().orElse(null);

                while (current != null) {

                    if (current instanceof TypeDeclaration<?> type) {
                        ownerParts.add(
                                0,
                                type.getNameAsString()
                        );
                    }

                    current =
                            current.getParentNode().orElse(null);
                }

                String owner = String.join(".", ownerParts);

                if (owner.isBlank()) {
                    owner = "<unknown-type>";
                }

                // The method signature distinguishes overloads.
                String symbol = owner + "."
                        + method.getSignature().asString();

                String locationId = file + ":"
                        + startLine + ":"
                        + endLine + ":"
                        + symbol;

                // ---------------------------------------
                // Detector 1: Long Method
                // ---------------------------------------
                // A configured boundary is used here.
                // This is preliminary detection, not a
                // scientifically calibrated threshold.
                if (metrics.ncss() > thresholds.maxNcss()) {

                    findings.add(
                            new MaintainabilityFinding(
                                    locationId + ":LONG_METHOD",
                                    MaintainabilityConcern.LONG_METHOD,
                                    FindingScope.METHOD,
                                    file,
                                    symbol,
                                    startLine,
                                    endLine,
                                    "METHOD_NCSS_BOUNDARY",
                                    "Method NCSS exceeds the configured "
                                            + "preliminary decision boundary.",
                                    Map.of(
                                            "ncss",
                                            String.valueOf(
                                                    metrics.ncss()
                                            ),
                                            "configuredMaxNcss",
                                            String.valueOf(
                                                    thresholds.maxNcss()
                                            ),
                                            "measurement",
                                            "preliminary_ast_ncss"
                                    )
                            )
                    );
                }

                // ---------------------------------------
                // Detector 2: High Complexity
                // ---------------------------------------
                // Uses the existing preliminary AST-based
                // cyclomatic complexity calculation.
                if (metrics.cyclomaticComplexity()
                        > thresholds.maxCyclomaticComplexity()) {

                    findings.add(
                            new MaintainabilityFinding(
                                    locationId + ":HIGH_COMPLEXITY",
                                    MaintainabilityConcern.HIGH_COMPLEXITY,
                                    FindingScope.METHOD,
                                    file,
                                    symbol,
                                    startLine,
                                    endLine,
                                    "METHOD_CYCLOMATIC_BOUNDARY",
                                    "Method cyclomatic complexity exceeds "
                                            + "the configured preliminary "
                                            + "decision boundary.",
                                    Map.of(
                                            "cyclomaticComplexity",
                                            String.valueOf(
                                                    metrics.cyclomaticComplexity()
                                            ),
                                            "configuredMaxComplexity",
                                            String.valueOf(
                                                    thresholds.maxCyclomaticComplexity()
                                            ),
                                            "measurement",
                                            "preliminary_ast_cyclomatic"
                                    )
                            )
                    );
                }
            }
        }

        return List.copyOf(findings);
    }
}
