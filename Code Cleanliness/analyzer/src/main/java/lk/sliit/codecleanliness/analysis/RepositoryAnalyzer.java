
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodMaintainabilityDetector;

import lk.sliit.codecleanliness.extraction.RepositoryRelationshipBuilder;
import lk.sliit.codecleanliness.extraction.RepositoryStructureBuilder;

import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public class RepositoryAnalyzer {

    private final JavaRepositoryParser parser;
    private final RepositoryStructureBuilder structureBuilder;
    private final RepositoryRelationshipBuilder relationshipBuilder;
    private final MethodMaintainabilityDetector methodDetector;

    public RepositoryAnalyzer() {
        this(
                new JavaRepositoryParser(),
                new RepositoryStructureBuilder(),
                new RepositoryRelationshipBuilder(),
                new MethodMaintainabilityDetector()
        );
    }

    // Preserve the original constructor.
    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder) {

        this(
                parser,
                structureBuilder,
                relationshipBuilder,
                new MethodMaintainabilityDetector()
        );
    }

    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder,
            MethodMaintainabilityDetector methodDetector) {

        this.parser = Objects.requireNonNull(parser);
        this.structureBuilder = Objects.requireNonNull(structureBuilder);
        this.relationshipBuilder = Objects.requireNonNull(
                relationshipBuilder
        );
        this.methodDetector = Objects.requireNonNull(methodDetector);
    }

    // Existing analysis behavior remains available.
    // No uncalibrated detector thresholds are applied.
    public RepositoryAnalysisResult analyze(Path repositoryRoot)
            throws IOException {

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(repositoryRoot);

        return new RepositoryAnalysisResult(
                parsed,
                structureBuilder.build(parsed),
                relationshipBuilder.build(parsed),
                List.of()
        );
    }

    // Explicitly configured preliminary detection.
    public RepositoryAnalysisResult analyze(
            Path repositoryRoot,
            MethodDetectionThresholds thresholds)
            throws IOException {

        Objects.requireNonNull(
                thresholds,
                "Detection thresholds are required"
        );

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(repositoryRoot);

        List<MaintainabilityFinding> findings =
                methodDetector.detect(parsed, thresholds);

        return new RepositoryAnalysisResult(
                parsed,
                structureBuilder.build(parsed),
                relationshipBuilder.build(parsed),
                findings
        );
    }
}
