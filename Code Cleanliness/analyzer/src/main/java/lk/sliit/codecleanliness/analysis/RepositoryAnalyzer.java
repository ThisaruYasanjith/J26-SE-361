
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassMaintainabilityDetector;
import lk.sliit.codecleanliness.detection.GodClassDetector;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodMaintainabilityDetector;
import lk.sliit.codecleanliness.detection.WeakCohesionDetector;
import lk.sliit.codecleanliness.detection.DuplicatedLogicDetector;
import lk.sliit.codecleanliness.detection.PoorNamingDetector;

import lk.sliit.codecleanliness.detection.SrpRiskDetector;
import lk.sliit.codecleanliness.detection.OcpRiskDetector;
import lk.sliit.codecleanliness.detection.LspRiskDetector;
import lk.sliit.codecleanliness.detection.IspRiskDetector;
import lk.sliit.codecleanliness.detection.DipRiskDetector;

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
 * Parses the entire repository once and returns:
 * - Java class and interface structures
 * - Relationships between Java types and methods
 * - Explicitly configured maintainability findings
 *
 * Supported preliminary concern categories:
 *
 *  1. Long Method
 *  2. High Complexity
 *  3. Large Class
 *  4. Weak Cohesion
 *  5. God Class
 *  6. Duplicated Logic
 *  7. Poor Naming
 *  8. SRP Risk
 *  9. OCP Risk
 * 10. LSP Risk
 * 11. ISP Risk
 * 12. DIP Risk
 *
 * SOLID detectors identify structural risk candidates,
 * not conclusively proven SOLID violations.
 *
 * Existing constructors and analysis methods are
 * preserved for backward compatibility.
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

    private final PoorNamingDetector poorNamingDetector =
            new PoorNamingDetector();

    private final SrpRiskDetector srpRiskDetector =
            new SrpRiskDetector();

    private final OcpRiskDetector ocpRiskDetector =
            new OcpRiskDetector();

    private final LspRiskDetector lspRiskDetector =
            new LspRiskDetector();

    private final IspRiskDetector ispRiskDetector =
            new IspRiskDetector();

    private final DipRiskDetector dipRiskDetector =
            new DipRiskDetector();

    /**
     * Default analyzer constructor.
     */
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
     * Fully injectable original detector constructor.
     *
     * Preserved for existing tests and integrations.
     */
    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder,
            MethodMaintainabilityDetector methodDetector,
            ClassMaintainabilityDetector classDetector,
            WeakCohesionDetector cohesionDetector,
            GodClassDetector godClassDetector) {

        this.parser =
                Objects.requireNonNull(parser);

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
     * Original structure-only repository analysis.
     *
     * Does not implicitly apply maintainability
     * detection thresholds.
     */
    public RepositoryAnalysisResult analyze(
            Path repositoryRoot) throws IOException {

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(
                        repositoryRoot
                );

        return buildResult(
                parsed,
                List.of()
        );
    }

    /**
     * Preserved method-level maintainability analysis.
     *
     * Supports Long Method and High Complexity
     * using explicitly supplied thresholds.
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

        return buildResult(
                parsed,
                findings
        );
    }

    /**
     * Unified repository-wide maintainability detection.
     *
     * Parses the repository once and reuses that
     * repository parse result across all enabled detectors.
     *
     * Duplicated Logic, Poor Naming and SOLID risk
     * detection are explicitly opt-in.
     *
     * All findings are sorted deterministically before
     * downstream grouping and prioritization.
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

        // 1. Long Method and High Complexity
        findings.addAll(
                methodDetector.detect(
                        parsed,
                        config.methodThresholds()
                )
        );

        // 2. Large Class
        findings.addAll(
                classDetector.detect(
                        parsed,
                        config.classThresholds()
                )
        );

        // 3. Weak Cohesion
        findings.addAll(
                cohesionDetector.detect(
                        parsed,
                        config.cohesionThresholds()
                )
        );

        // 4. God Class
        findings.addAll(
                godClassDetector.detect(
                        parsed,
                        config.godClassThresholds()
                )
        );

        // 5. Duplicated Logic (optional)
        if (config.duplicateDetectionEnabled()) {
            findings.addAll(
                    duplicatedLogicDetector.detect(
                            parsed,
                            config.duplicateThresholds()
                    )
            );
        }

        // 6. Poor Naming (optional)
        if (config.namingDetectionEnabled()) {
            findings.addAll(
                    poorNamingDetector.detect(
                            parsed,
                            config.namingConfig()
                    )
            );
        }

        // 7. Preliminary SOLID structural risks (optional)
        if (config.solidRisksEnabled()) {

            // Single Responsibility Principle
            findings.addAll(
                    srpRiskDetector.detect(parsed)
            );

            // Open/Closed Principle
            findings.addAll(
                    ocpRiskDetector.detect(parsed)
            );

            // Liskov Substitution Principle
            findings.addAll(
                    lspRiskDetector.detect(parsed)
            );

            // Interface Segregation Principle
            findings.addAll(
                    ispRiskDetector.detect(parsed)
            );

            // Dependency Inversion Principle
            findings.addAll(
                    dipRiskDetector.detect(parsed)
            );
        }

        // Stable ordering across repository executions.
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
     *
     * Builds structural information and relationships
     * from the same parsed repository.
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
