
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
 * Current pipeline:
 * Detection -> Related-Issue Grouping -> Priority Ranking
 *
 * The detectors and preliminary triage algorithms remain
 * separately testable and independently configurable.
 */
public class RepositoryTriageService {

    private final RepositoryAnalyzer analyzer;
    private final RelatedIssueGrouper grouper;
    private final MaintainabilityPriorityRanker ranker;

    public RepositoryTriageService() {
        this(
                new RepositoryAnalyzer(),
                new RelatedIssueGrouper(),
                new MaintainabilityPriorityRanker()
        );
    }

    public RepositoryTriageService(
            RepositoryAnalyzer analyzer,
            RelatedIssueGrouper grouper,
            MaintainabilityPriorityRanker ranker
    ) {
        this.analyzer = Objects.requireNonNull(analyzer);
        this.grouper = Objects.requireNonNull(grouper);
        this.ranker = Objects.requireNonNull(ranker);
    }

    /**
     * Runs a full repository-wide preliminary triage.
     *
     * All detection boundaries must be explicitly supplied.
     */
    public RepositoryTriageResult analyze(
            Path repositoryRoot,
            RepositoryDetectionConfig config
    ) throws IOException {

        Objects.requireNonNull(
                repositoryRoot, "Repository path is required"
        );
        Objects.requireNonNull(
                config, "Detection configuration is required"
        );

        RepositoryAnalysisResult analysis =
                analyzer.analyze(repositoryRoot, config);

        List<IssueGroup> groups =
                grouper.group(analysis.findings());

        List<RankedIssueGroup> ranked =
                ranker.rank(groups);

        return new RepositoryTriageResult(
                analysis,
                groups,
                ranked
        );
    }
}
