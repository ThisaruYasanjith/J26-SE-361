
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import lk.sliit.codecleanliness.extraction.MethodUsageExtractor;

import lk.sliit.codecleanliness.metrics.AtfdMetrics;
import lk.sliit.codecleanliness.metrics.AtfdMetricsCalculator;
import lk.sliit.codecleanliness.metrics.ClassMetrics;
import lk.sliit.codecleanliness.metrics.ClassMetricsCalculator;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class GodClassDetector {

    private final ClassMetricsCalculator classCalculator;
    private final AtfdMetricsCalculator atfdCalculator;
    private final MethodUsageExtractor usageExtractor;
    private final CohesionMetricsCalculator cohesionCalculator;

    public GodClassDetector() {
        this(
                new ClassMetricsCalculator(),
                new AtfdMetricsCalculator(),
                new MethodUsageExtractor(),
                new CohesionMetricsCalculator()
        );
    }

    public GodClassDetector(
            ClassMetricsCalculator classCalculator,
            AtfdMetricsCalculator atfdCalculator,
            MethodUsageExtractor usageExtractor,
            CohesionMetricsCalculator cohesionCalculator) {

        this.classCalculator = Objects.requireNonNull(classCalculator);
        this.atfdCalculator = Objects.requireNonNull(atfdCalculator);
        this.usageExtractor = Objects.requireNonNull(usageExtractor);
        this.cohesionCalculator =
                Objects.requireNonNull(cohesionCalculator);
    }

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            GodClassDetectionThresholds thresholds) {

        Objects.requireNonNull(repository);
        Objects.requireNonNull(thresholds);

        List<MethodUsageInfo> usages =
                usageExtractor.extract(repository);

        List<MaintainabilityFinding> findings = new ArrayList<>();

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

                if (declaration.isInterface()
                        || declaration.getRange().isEmpty()
                        || declaration.getMethods().size() < 2) {
                    continue;
                }

                if (declaration.getMethods().stream()
                        .anyMatch(method -> method.getBody().isEmpty())) {
                    continue;
                }

                String className = declaration
                        .getFullyQualifiedName()
                        .orElse(declaration.getNameAsString());

                List<MethodUsageInfo> classUsages = usages.stream()
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

                // Incomplete references can make both
                // cohesion and foreign-field evidence unreliable.
                if (classUsages.stream().anyMatch(usage ->
                        !usage.unresolvedReferences().isEmpty())) {
                    continue;
                }

                ClassMetrics classMetrics =
                        classCalculator.calculate(declaration);

                AtfdMetrics atfdMetrics =
                        atfdCalculator.calculate(declaration);

                if (atfdMetrics.unresolvedReferences() > 0) {
                    continue;
                }

                CohesionMetrics cohesionMetrics =
                        cohesionCalculator.calculate(
                                className,
                                classUsages
                        );

                if (cohesionMetrics.possibleMethodPairs() == 0) {
                    continue;
                }

                boolean highWmc =
                        classMetrics.weightedMethodCount()
                                >= thresholds.minWmc();

                boolean highAtfd =
                        atfdMetrics.distinctForeignFields()
                                >= thresholds.minAtfd();

                boolean lowTcc =
                        cohesionMetrics.tcc() < thresholds.maxTcc();

                if (!highWmc || !highAtfd || !lowTcc) {
                    continue;
                }

                int startLine = declaration.getRange()
                        .orElseThrow().begin.line;

                int endLine = declaration.getRange()
                        .orElseThrow().end.line;

                String findingId = sourceFile + ":"
                        + startLine + ":" + endLine
                        + ":" + className + ":GOD_CLASS";

                Map<String, String> evidence =
                        new LinkedHashMap<>();

                evidence.put(
                        "wmc",
                        String.valueOf(
                                classMetrics.weightedMethodCount()
                        )
                );

                evidence.put(
                        "atfd",
                        String.valueOf(
                                atfdMetrics.distinctForeignFields()
                        )
                );

                evidence.put(
                        "tcc",
                        String.valueOf(cohesionMetrics.tcc())
                );

                evidence.put(
                        "methodCount",
                        String.valueOf(classMetrics.methodCount())
                );

                evidence.put(
                        "configuredMinWmc",
                        String.valueOf(thresholds.minWmc())
                );

                evidence.put(
                        "configuredMinAtfd",
                        String.valueOf(thresholds.minAtfd())
                );

                evidence.put(
                        "configuredMaxTcc",
                        String.valueOf(thresholds.maxTcc())
                );

                evidence.put("unresolvedReferences", "0");

                evidence.put(
                        "measurement",
                        "preliminary_wmc_atfd_tcc"
                );

                findings.add(
                        new MaintainabilityFinding(
                                findingId,
                                MaintainabilityConcern.GOD_CLASS,
                                FindingScope.CLASS,
                                sourceFile,
                                className,
                                startLine,
                                endLine,
                                "GOD_CLASS_COMPOSITE_BOUNDARY",
                                "Class satisfies the configured "
                                        + "preliminary WMC, ATFD and "
                                        + "TCC God Class candidate rule.",
                                evidence
                        )
                );
            }
        }

        return List.copyOf(findings);
    }
}
