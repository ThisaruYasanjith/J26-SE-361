
package lk.sliit.codecleanliness.triage;

import java.util.Objects;

/**
 * A maintainability issue group with an interpretable,
 * preliminary, evidence-based priority ranking.
 *
 * Lower rank numbers indicate higher review priority.
 */
public record RankedIssueGroup(
        int rank,
        IssueGroup group,
        double exceedanceScore,
        int distinctConcernCount,
        int affectedFileCount,
        int supportedFindingCount,
        String explanation
) {

    public RankedIssueGroup {
        if (rank < 1) {
            throw new IllegalArgumentException(
                    "Rank must be positive"
            );
        }

        Objects.requireNonNull(group, "Issue group is required");

        if (!Double.isFinite(exceedanceScore)
                || exceedanceScore < 0.0
                || exceedanceScore > 1.0) {
            throw new IllegalArgumentException(
                    "Exceedance score must be between 0 and 1"
            );
        }

        if (distinctConcernCount < 1
                || affectedFileCount < 1
                || supportedFindingCount < 0
                || supportedFindingCount > group.findingCount()) {
            throw new IllegalArgumentException(
                    "Invalid priority factor values"
            );
        }

        if (explanation == null || explanation.isBlank()) {
            throw new IllegalArgumentException(
                    "Priority explanation is required"
            );
        }
    }
}
