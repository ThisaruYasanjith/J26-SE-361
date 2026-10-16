
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
 * Detection -> Evidence-Aware Grouping -> Priority Ranking
 *
 * Grouping supports exact-location and preliminary
 * class-method contextual relationships.
 *
 * Detection thresholds and priority factors are
 * preliminary and require empirical evaluation.
 */
public class RepositoryTriageService {

    private final RepositoryAnalyzer analyzer;
    private final EvidenceAwareIssueGrouper grouper;
    private final MaintainabilityPriorityRanker ranker;

    public RepositoryTriageService() {
        this(
                new RepositoryAnalyzer(),
                new EvidenceAwareIssueGrouper(),
                new MaintainabilityPriorityRanker()
        );
    }

    public RepositoryTriageService(
            RepositoryAnalyzer analyzer,
            EvidenceAwareIssueGrouper grouper,
            MaintainabilityPriorityRanker ranker
    ) {
        this.analyzer = Objects.requireNonNull(
                analyzer, "Repository analyzer is required"
        );
        this.grouper = Objects.requireNonNull(
                grouper, "Issue grouper is required"
        );
        this.ranker = Objects.requireNonNull(
                ranker, "Priority ranker is required"
        );
    }

    /**
     * Performs preliminary maintainability triage over
     * all Java files discovered in the repository.
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

        RepositoryAnalysisResult analysis =
                analyzer.analyze(repositoryRoot, config);

        List<IssueGroup> groups =
                grouper.group(analysis.findings());

        List<RankedIssueGroup> rankedGroups =
                ranker.rank(groups);

        return new RepositoryTriageResult(
                analysis,
                groups,
                rankedGroups
        );
    }
}
