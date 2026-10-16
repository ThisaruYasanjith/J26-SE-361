
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import lk.sliit.codecleanliness.extraction.MethodUsageExtractor;
import lk.sliit.codecleanliness.metrics.CohesionMetrics;
import lk.sliit.codecleanliness.metrics.CohesionMetricsCalculator;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.MethodUsageInfo;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class WeakCohesionDetector {

    private final MethodUsageExtractor usageExtractor;
    private final CohesionMetricsCalculator cohesionCalculator;

    public WeakCohesionDetector() {
        this(
                new MethodUsageExtractor(),
                new CohesionMetricsCalculator()
        );
    }

    public WeakCohesionDetector(
            MethodUsageExtractor usageExtractor,
            CohesionMetricsCalculator cohesionCalculator) {

        this.usageExtractor =
                Objects.requireNonNull(usageExtractor);

        this.cohesionCalculator =
                Objects.requireNonNull(cohesionCalculator);
    }

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            CohesionDetectionThresholds thresholds) {

        Objects.requireNonNull(repository);
        Objects.requireNonNull(thresholds);

        List<MethodUsageInfo> allUsages =
                usageExtractor.extract(repository);

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        List<Map.Entry<Path, CompilationUnit>> files =
                repository.parsedFiles()
                        .entrySet()
                        .stream()
                        .sorted(
                                Comparator.comparing(
                                        entry -> entry.getKey().toString()
                                )
                        )
                        .toList();

        for (Map.Entry<Path, CompilationUnit> entry : files) {

            Path sourceFile = entry.getKey()
                    .toAbsolutePath()
                    .normalize();

            for (ClassOrInterfaceDeclaration declaration :
                    entry.getValue()
                            .findAll(ClassOrInterfaceDeclaration.class)) {

                if (declaration.isInterface()) {
                    continue;
                }

                if (declaration.getRange().isEmpty()) {
                    continue;
                }

                // The current usage extractor and metric
                // calculator operate on declared methods.
                // Classes with fewer than two methods
                // have insufficient method-pair evidence.
                if (declaration.getMethods().size() < 2) {
                    continue;
                }

                // Avoid treating abstract or bodyless
                // methods as disconnected implementations.
                if (declaration.getMethods().stream()
                        .anyMatch(method -> method.getBody().isEmpty())) {
                    continue;
                }

                String className = declaration
                        .getFullyQualifiedName()
                        .orElse(declaration.getNameAsString());

                List<MethodUsageInfo> classUsages =
                        allUsages.stream()
                                .filter(usage ->
                                        className.equals(usage.ownerType())
                                        && entry.getKey().equals(
                                                usage.sourceFile()
                                        )
                                )
                                .toList();

                if (classUsages.size()
                        != declaration.getMethods().size()) {
                    continue;
                }

                // Incomplete symbol resolution could hide
                // field-sharing or method-call edges.
                boolean unresolved = classUsages.stream()
                        .anyMatch(usage ->
                                !usage.unresolvedReferences().isEmpty()
                        );

                if (unresolved) {
                    continue;
                }

                CohesionMetrics metrics =
                        cohesionCalculator.calculate(
                                className,
                                classUsages
                        );

                if (metrics.possibleMethodPairs() == 0) {
                    continue;
                }

                boolean lowTcc =
                        metrics.tcc() < thresholds.maxTcc();

                boolean multipleComponents =
                        metrics.lcom4() >= thresholds.minLcom4();

                if (!lowTcc || !multipleComponents) {
                    continue;
                }

                int startLine = declaration.getRange()
                        .orElseThrow().begin.line;

                int endLine = declaration.getRange()
                        .orElseThrow().end.line;

                String findingId = sourceFile + ":"
                        + startLine + ":"
                        + endLine + ":"
                        + className + ":WEAK_COHESION";

                findings.add(
                        new MaintainabilityFinding(
                                findingId,
                                MaintainabilityConcern.WEAK_COHESION,
                                FindingScope.CLASS,
                                sourceFile,
                                className,
                                startLine,
                                endLine,
                                "CLASS_COHESION_BOUNDARY",
                                "Class satisfies the configured "
                                        + "preliminary weak-cohesion "
                                        + "candidate criteria.",
                                Map.of(
                                        "methodCount",
                                        String.valueOf(metrics.methodCount()),
                                        "possibleMethodPairs",
                                        String.valueOf(
                                                metrics.possibleMethodPairs()
                                        ),
                                        "connectedMethodPairs",
                                        String.valueOf(
                                                metrics.connectedMethodPairs()
                                        ),
                                        "tcc",
                                        String.valueOf(metrics.tcc()),
                                        "lcom4",
                                        String.valueOf(metrics.lcom4()),
                                        "configuredMaxTcc",
                                        String.valueOf(thresholds.maxTcc()),
                                        "configuredMinLcom4",
                                        String.valueOf(thresholds.minLcom4()),
                                        "unresolvedReferences",
                                        "0",
                                        "measurement",
                                        "preliminary_cohesion_graph"
                                )
                        )
                );
            }
        }

        return List.copyOf(findings);
    }
}
