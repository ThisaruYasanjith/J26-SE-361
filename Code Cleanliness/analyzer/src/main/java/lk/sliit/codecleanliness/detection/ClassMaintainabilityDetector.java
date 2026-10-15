
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import lk.sliit.codecleanliness.metrics.ClassMetrics;
import lk.sliit.codecleanliness.metrics.ClassMetricsCalculator;

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

public class ClassMaintainabilityDetector {

    private final ClassMetricsCalculator calculator;

    public ClassMaintainabilityDetector() {
        this(new ClassMetricsCalculator());
    }

    public ClassMaintainabilityDetector(
            ClassMetricsCalculator calculator) {

        this.calculator = Objects.requireNonNull(calculator);
    }

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            ClassDetectionThresholds thresholds) {

        Objects.requireNonNull(repository, "Repository is required");
        Objects.requireNonNull(thresholds, "Thresholds are required");

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

            CompilationUnit unit = entry.getValue();

            for (ClassOrInterfaceDeclaration declaration :
                    unit.findAll(ClassOrInterfaceDeclaration.class)) {

                // Interface contracts are not evaluated
                // using this preliminary class-size rule.
                if (declaration.isInterface()) {
                    continue;
                }

                if (declaration.getRange().isEmpty()) {
                    continue;
                }

                ClassMetrics metrics =
                        calculator.calculate(declaration);

                int startLine = declaration.getRange()
                        .orElseThrow().begin.line;

                int endLine = declaration.getRange()
                        .orElseThrow().end.line;

                String className = declaration
                        .getFullyQualifiedName()
                        .orElse(metrics.qualifiedClassName());

                boolean exceedsNcss =
                        metrics.classNcss() > thresholds.maxClassNcss();

                boolean exceedsMethods =
                        metrics.methodCount() > thresholds.maxMethodCount();

                boolean exceedsFields =
                        metrics.fieldCount() > thresholds.maxFieldCount();

                // Preliminary OR rule: any exceeded boundary
                // creates a candidate Large Class finding.
                if (!exceedsNcss
                        && !exceedsMethods
                        && !exceedsFields) {
                    continue;
                }

                String findingId = sourceFile + ":"
                        + startLine + ":"
                        + endLine + ":"
                        + className + ":LARGE_CLASS";

                findings.add(
                        new MaintainabilityFinding(
                                findingId,
                                MaintainabilityConcern.LARGE_CLASS,
                                FindingScope.CLASS,
                                sourceFile,
                                className,
                                startLine,
                                endLine,
                                "CLASS_SIZE_BOUNDARY",
                                "Class exceeds at least one "
                                        + "configured preliminary "
                                        + "class-size boundary.",
                                Map.of(
                                        "classNcss",
                                        String.valueOf(metrics.classNcss()),
                                        "methodCount",
                                        String.valueOf(metrics.methodCount()),
                                        "fieldCount",
                                        String.valueOf(metrics.fieldCount()),
                                        "maxClassNcss",
                                        String.valueOf(thresholds.maxClassNcss()),
                                        "maxMethodCount",
                                        String.valueOf(thresholds.maxMethodCount()),
                                        "maxFieldCount",
                                        String.valueOf(thresholds.maxFieldCount()),
                                        "exceedsNcss",
                                        String.valueOf(exceedsNcss),
                                        "exceedsMethods",
                                        String.valueOf(exceedsMethods),
                                        "exceedsFields",
                                        String.valueOf(exceedsFields),
                                        "measurement",
                                        "preliminary_class_size"
                                )
                        )
                );
            }
        }

        return List.copyOf(findings);
    }
}
