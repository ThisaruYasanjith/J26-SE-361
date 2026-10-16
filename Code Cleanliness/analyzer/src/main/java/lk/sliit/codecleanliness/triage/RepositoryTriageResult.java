
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;

import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Combined output from repository-level maintainability triage.
 *
 * Preserves the original repository analysis evidence,
 * the related-issue groups, and their priority ranking.
 */
public record RepositoryTriageResult(
        RepositoryAnalysisResult analysis,
        List<IssueGroup> groups,
        List<RankedIssueGroup> rankedGroups
) {

    public RepositoryTriageResult {
        Objects.requireNonNull(
                analysis, "Repository analysis is required"
        );
        Objects.requireNonNull(groups, "Groups are required");
        Objects.requireNonNull(
                rankedGroups, "Ranked groups are required"
        );

        groups = List.copyOf(groups);
        rankedGroups = List.copyOf(rankedGroups);

        if (groups.size() != rankedGroups.size()) {
            throw new IllegalArgumentException(
                    "Every issue group must have one ranking"
            );
        }

        Set<String> groupIds = groups.stream()
                .map(IssueGroup::groupId)
                .collect(Collectors.toSet());

        Set<String> rankedIds = rankedGroups.stream()
                .map(entry -> entry.group().groupId())
                .collect(Collectors.toSet());

        if (groupIds.size() != groups.size()
                || rankedIds.size() != rankedGroups.size()
                || !groupIds.equals(rankedIds)) {
            throw new IllegalArgumentException(
                    "Group and ranking identifiers must match uniquely"
            );
        }

        for (int index = 0; index < rankedGroups.size(); index++) {
            if (rankedGroups.get(index).rank() != index + 1) {
                throw new IllegalArgumentException(
                        "Ranks must be sequential starting from 1"
                );
            }
        }

        Set<String> findingIds = analysis.findings().stream()
                .map(finding -> finding.findingId())
                .collect(Collectors.toSet());

        Set<String> groupedFindingIds = groups.stream()
                .flatMap(group -> group.findings().stream())
                .map(finding -> finding.findingId())
                .collect(Collectors.toSet());

        int groupedFindingCount = groups.stream()
                .mapToInt(IssueGroup::findingCount)
                .sum();

        if (findingIds.size() != analysis.findingCount()
                || groupedFindingCount != analysis.findingCount()
                || !findingIds.equals(groupedFindingIds)) {
            throw new IllegalArgumentException(
                    "Every detected finding must appear in exactly one group"
            );
        }
    }

    public int findingCount() {
        return analysis.findingCount();
    }

    public int groupCount() {
        return groups.size();
    }
}
