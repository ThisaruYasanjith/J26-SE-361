
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Preliminary deterministic related-issue grouping.
 *
 * The current algorithm groups findings only when
 * they have the same scope, normalized source file,
 * symbol name, and source range.
 *
 * It does not infer cross-file or dependency-based
 * relationships. Those require separate evidence.
 */
public class RelatedIssueGrouper {

    public List<IssueGroup> group(
            List<MaintainabilityFinding> findings) {

        Objects.requireNonNull(
                findings,
                "Maintainability findings are required"
        );

        List<MaintainabilityFinding> ordered =
                findings.stream()
                        .map(Objects::requireNonNull)
                        .sorted(
                                Comparator
                                        .comparing(
                                                MaintainabilityFinding::findingId
                                        )
                        )
                        .toList();

        Map<GroupingKey, List<MaintainabilityFinding>>
                buckets = new LinkedHashMap<>();

        for (MaintainabilityFinding finding : ordered) {

            GroupingKey key = keyFor(finding);

            buckets.computeIfAbsent(
                    key,
                    ignored -> new ArrayList<>()
            ).add(finding);
        }

        List<IssueGroup> groups = new ArrayList<>();

        for (Map.Entry<
                GroupingKey,
                List<MaintainabilityFinding>> entry
                : buckets.entrySet()) {

            List<MaintainabilityFinding> members =
                    List.copyOf(entry.getValue());

            // Use an existing finding identifier
            // as the stable anchor for this group.
            String groupId =
                    "GROUP:" + members.get(0).findingId();

            String relationshipType;
            String explanation;

            if (members.size() == 1) {
                relationshipType = "SINGLE_FINDING";
                explanation =
                        "No other finding shares this "
                        + "verified code location.";
            } else if (
                    members.get(0).scope() == FindingScope.METHOD) {

                relationshipType = "SAME_METHOD";
                explanation =
                        "Findings refer to the same method "
                        + "at the same source location.";
            } else if (
                    members.get(0).scope() == FindingScope.CLASS) {

                relationshipType = "SAME_CLASS";
                explanation =
                        "Findings refer to the same class "
                        + "at the same source location.";
            } else {
                // Other finding scopes are deliberately
                // not merged at this preliminary stage.
                relationshipType = "SINGLE_FINDING";
                explanation =
                        "No supported direct grouping "
                        + "relationship is established.";
            }

            groups.add(
                    new IssueGroup(
                            groupId,
                            relationshipType,
                            explanation,
                            members
                    )
            );
        }

        return List.copyOf(groups);
    }

    private GroupingKey keyFor(
            MaintainabilityFinding finding) {

        Path file = finding.sourceFile()
                .toAbsolutePath()
                .normalize();

        if (finding.scope() == FindingScope.METHOD
                || finding.scope() == FindingScope.CLASS) {

            return new GroupingKey(
                    file.toString(),
                    finding.scope().name(),
                    finding.symbolName(),
                    finding.startLine(),
                    finding.endLine(),
                    ""
            );
        }

        // Unsupported scopes remain separate, even
        // when their source ranges happen to overlap.
        return new GroupingKey(
                file.toString(),
                finding.scope().name(),
                finding.symbolName(),
                finding.startLine(),
                finding.endLine(),
                finding.findingId()
        );
    }

    private record GroupingKey(
            String sourceFile,
            String scope,
            String symbol,
            int startLine,
            int endLine,
            String isolatedFindingId
    ) {}
}
