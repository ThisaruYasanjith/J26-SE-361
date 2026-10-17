
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.analysis.RepositoryAnalyzer;
import lk.sliit.codecleanliness.analysis.RepositoryDetectionConfig;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

/**
 * Coordinates repository-wide maintainability triage.
 *
 * Pipeline:
 *
 * 1. Repository-wide maintainability detection
 * 2. Evidence-aware exact-location and class-method grouping
 * 3. Evidence-based cross-file duplicated logic grouping
 * 4. Interpretable priority ranking
 *
 * Cross-file grouping currently supports identical
 * normalized method-body fingerprints across Java files.
 *
 * It does not infer arbitrary cross-file dependencies
 * or establish verified common root causes.
 *
 * Detection thresholds, grouping rules and priority
 * factors remain preliminary and require empirical
 * evaluation.
 */
public class RepositoryTriageService {

    private final RepositoryAnalyzer analyzer;

    private final EvidenceAwareIssueGrouper grouper;

    private final CrossFileDuplicateIssueGrouper crossFileGrouper =
            new CrossFileDuplicateIssueGrouper();

    private final MaintainabilityPriorityRanker ranker;

    /**
     * Default constructor.
     */
    public RepositoryTriageService() {
        this(
                new RepositoryAnalyzer(),
                new EvidenceAwareIssueGrouper(),
                new MaintainabilityPriorityRanker()
        );
    }

    /**
     * Preserved original constructor for existing tests
     * and integrations.
     */
    public RepositoryTriageService(
            RepositoryAnalyzer analyzer,
            EvidenceAwareIssueGrouper grouper,
            MaintainabilityPriorityRanker ranker
    ) {
        this.analyzer = Objects.requireNonNull(
                analyzer,
                "Repository analyzer is required"
        );

        this.grouper = Objects.requireNonNull(
                grouper,
                "Issue grouper is required"
        );

        this.ranker = Objects.requireNonNull(
                ranker,
                "Priority ranker is required"
        );
    }

    /**
     * Performs maintainability triage across all
     * Java files discovered in the repository.
     *
     * The same analysis result is used throughout
     * grouping and ranking.
     *
     * Every finding must appear exactly once in
     * the final grouping result.
     */
    public RepositoryTriageResult analyze(
            Path repositoryRoot,
            RepositoryDetectionConfig config
    ) throws IOException {

        Objects.requireNonNull(
                repositoryRoot,
                "Repository root is required"
        );

        Objects.requireNonNull(
                config,
                "Detection configuration is required"
        );

        // Stage 1: Analyze the repository once.
        RepositoryAnalysisResult analysis =
                analyzer.analyze(repositoryRoot, config);

        // Stage 2: Group findings by exact location
        // and supported class-method relationships.
        List<IssueGroup> contextualGroups =
                grouper.group(analysis.findings());

        // Stage 3: Identify cross-file duplicated logic
        // through shared normalized body fingerprints.
        //
        // This stage preserves every original finding
        // exactly once.
        List<IssueGroup> groups =
                crossFileGrouper.group(contextualGroups);

        // Stage 4: Rank the resulting issue groups
        // using the existing interpretable ranker.
        List<RankedIssueGroup> rankedGroups =
                ranker.rank(groups);

        // Preserve the existing result structure.
        return new RepositoryTriageResult(
                analysis,
                groups,
                rankedGroups
        );
    }
}
