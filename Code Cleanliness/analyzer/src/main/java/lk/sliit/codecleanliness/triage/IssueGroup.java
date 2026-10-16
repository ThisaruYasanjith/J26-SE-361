
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * An evidence-linked group of maintainability findings.
 *
 * A singleton group represents a finding without another
 * directly related finding at the current grouping stage.
 */
public record IssueGroup(
        String groupId,
        String relationshipType,
        String explanation,
        List<MaintainabilityFinding> findings
) {

    public IssueGroup {
        if (groupId == null || groupId.isBlank()) {
            throw new IllegalArgumentException(
                    "Group ID must not be blank"
            );
        }

        if (relationshipType == null
                || relationshipType.isBlank()) {
            throw new IllegalArgumentException(
                    "Relationship type must not be blank"
            );
        }

        if (explanation == null
                || explanation.isBlank()) {
            throw new IllegalArgumentException(
                    "Grouping explanation must not be blank"
            );
        }

        Objects.requireNonNull(findings);

        findings = List.copyOf(findings);

        if (findings.isEmpty()) {
            throw new IllegalArgumentException(
                    "Issue group must contain at least one finding"
            );
        }

        Set<String> ids = new HashSet<>();

        for (MaintainabilityFinding finding : findings) {
            Objects.requireNonNull(finding);

            if (!ids.add(finding.findingId())) {
                throw new IllegalArgumentException(
                        "Duplicate finding ID inside issue group"
                );
            }
        }
    }

    public int findingCount() {
        return findings.size();
    }

    public boolean containsRelatedFindings() {
        return findings.size() > 1;
    }
}
