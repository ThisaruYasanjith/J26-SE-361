
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassMaintainabilityDetector;
import lk.sliit.codecleanliness.detection.GodClassDetector;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodMaintainabilityDetector;
import lk.sliit.codecleanliness.detection.WeakCohesionDetector;
import lk.sliit.codecleanliness.detection.DuplicatedLogicDetector;

import lk.sliit.codecleanliness.extraction.RepositoryRelationshipBuilder;
import lk.sliit.codecleanliness.extraction.RepositoryStructureBuilder;

import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

/**
 * Repository-level Java maintainability analysis.
 *
 * Parses the repository once and returns structure,
 * relationships, and explicitly configured findings.
 */
public class RepositoryAnalyzer {

    private final JavaRepositoryParser parser;

    private final RepositoryStructureBuilder structureBuilder;

    private final RepositoryRelationshipBuilder relationshipBuilder;

    private final MethodMaintainabilityDetector methodDetector;

    private final ClassMaintainabilityDetector classDetector;

    private final WeakCohesionDetector cohesionDetector;

    private final GodClassDetector godClassDetector;

    private final DuplicatedLogicDetector duplicatedLogicDetector =
        new DuplicatedLogicDetector();

    public RepositoryAnalyzer() {
        this(
                new JavaRepositoryParser(),
                new RepositoryStructureBuilder(),
                new RepositoryRelationshipBuilder(),
                new MethodMaintainabilityDetector(),
                new ClassMaintainabilityDetector(),
                new WeakCohesionDetector(),
                new GodClassDetector()
        );
    }

    /**
     * Preserved original constructor.
     */
    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder) {

        this(
                parser,
                structureBuilder,
                relationshipBuilder,
                new MethodMaintainabilityDetector(),
                new ClassMaintainabilityDetector(),
                new WeakCohesionDetector(),
                new GodClassDetector()
        );
    }

    /**
     * Preserved method-detector constructor.
     */
    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder,
            MethodMaintainabilityDetector methodDetector) {

        this(
                parser,
                structureBuilder,
                relationshipBuilder,
                methodDetector,
                new ClassMaintainabilityDetector(),
                new WeakCohesionDetector(),
                new GodClassDetector()
        );
    }

    /**
     * Fully injectable constructor for testing and
     * future detector integration.
     */
    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder,
            MethodMaintainabilityDetector methodDetector,
            ClassMaintainabilityDetector classDetector,
            WeakCohesionDetector cohesionDetector,
            GodClassDetector godClassDetector) {

        this.parser = Objects.requireNonNull(parser);

        this.structureBuilder =
                Objects.requireNonNull(structureBuilder);

        this.relationshipBuilder =
                Objects.requireNonNull(relationshipBuilder);

        this.methodDetector =
                Objects.requireNonNull(methodDetector);

        this.classDetector =
                Objects.requireNonNull(classDetector);

        this.cohesionDetector =
                Objects.requireNonNull(cohesionDetector);

        this.godClassDetector =
                Objects.requireNonNull(godClassDetector);
    }

    /**
     * Original structure-only analysis.
     *
     * No preliminary detection thresholds are
     * applied implicitly.
     */
    public RepositoryAnalysisResult analyze(
            Path repositoryRoot) throws IOException {

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(
                        repositoryRoot
                );

        return buildResult(parsed, List.of());
    }

    /**
     * Original explicitly configured method-level
     * detection, preserved for compatibility.
     */
    public RepositoryAnalysisResult analyze(
            Path repositoryRoot,
            MethodDetectionThresholds thresholds)
            throws IOException {

        Objects.requireNonNull(
                thresholds,
                "Detection thresholds are required"
        );

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(
                        repositoryRoot
                );

        List<MaintainabilityFinding> findings =
                methodDetector.detect(
                        parsed,
                        thresholds
                );

        return buildResult(parsed, findings);
    }

    /**
     * Unified preliminary detection for five concerns:
     *
     * Long Method
     * High Complexity
     * Large Class
     * Weak Cohesion
     * God Class
     *
     * Every detector receives the same repository parse.
     */
    public RepositoryAnalysisResult analyze(
            Path repositoryRoot,
            RepositoryDetectionConfig config)
            throws IOException {

        Objects.requireNonNull(
                config,
                "Repository detection configuration is required"
        );

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(
                        repositoryRoot
                );

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        findings.addAll(
                methodDetector.detect(
                        parsed,
                        config.methodThresholds()
                )
        );

        findings.addAll(
                classDetector.detect(
                        parsed,
                        config.classThresholds()
                )
        );

        findings.addAll(
                cohesionDetector.detect(
                        parsed,
                        config.cohesionThresholds()
                )
        );

        findings.addAll(
                godClassDetector.detect(
                        parsed,
                        config.godClassThresholds()
                )
        );

        if (config.duplicateDetectionEnabled()) {
        findings.addAll(
                duplicatedLogicDetector.detect(
                        parsed,
                        config.duplicateThresholds()
                )
        );
        }

        // Stable ordering makes results reproducible
        // independently of map traversal order.
        findings.sort(
                Comparator
                        .comparing(
                                (MaintainabilityFinding finding) ->
                                        finding.sourceFile().toString()
                        )
                        .thenComparingInt(
                                MaintainabilityFinding::startLine
                        )
                        .thenComparing(
                                finding ->
                                        finding.concern().name()
                        )
                        .thenComparing(
                                MaintainabilityFinding::findingId
                        )
        );

        return buildResult(
                parsed,
                List.copyOf(findings)
        );
    }

    /**
     * Shared result assembly.
     */
    private RepositoryAnalysisResult buildResult(
            RepositoryParseResult parsed,
            List<MaintainabilityFinding> findings) {

        return new RepositoryAnalysisResult(
                parsed,
                structureBuilder.build(parsed),
                relationshipBuilder.build(parsed),
                findings
        );
    }
}
