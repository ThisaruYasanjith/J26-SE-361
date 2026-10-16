
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Preliminary evidence-aware maintainability grouping.
 *
 * First groups findings by exact location using the
 * existing RelatedIssueGrouper.
 *
 * Then creates class-context clusters when a class-level
 * finding structurally contains method-level findings.
 *
 * This is a contextual association, not proof of a
 * shared root cause or required refactoring action.
 *
 * Cross-file dependencies are deliberately not inferred.
 */
public class EvidenceAwareIssueGrouper {

    private final RelatedIssueGrouper baseGrouper;

    public EvidenceAwareIssueGrouper() {
        this(new RelatedIssueGrouper());
    }

    public EvidenceAwareIssueGrouper(
            RelatedIssueGrouper baseGrouper) {
        this.baseGrouper =
                Objects.requireNonNull(baseGrouper);
    }

    public List<IssueGroup> group(
            List<MaintainabilityFinding> findings) {

        Objects.requireNonNull(findings);

        List<IssueGroup> base =
                baseGrouper.group(findings);

        // Each base group is already an exact-location
        // partition of the original findings.
        Map<String, IssueGroup> byId =
                new LinkedHashMap<>();

        for (IssueGroup group : base) {
            if (byId.putIfAbsent(
                    group.groupId(), group) != null) {
                throw new IllegalArgumentException(
                        "Duplicate base group identifier"
                );
            }
        }

        List<IssueGroup> classes = base.stream()
                .filter(group ->
                        group.findings().get(0).scope()
                                == FindingScope.CLASS)
                .toList();

        Map<String, String> parentByGroup =
                new HashMap<>();

        // Only method groups can be attached to a
        // directly enclosing, affected class.
        for (IssueGroup candidate : base) {

            MaintainabilityFinding method =
                    candidate.findings().get(0);

            if (method.scope() != FindingScope.METHOD) {
                continue;
            }

            IssueGroup bestParent = null;
            int smallestRange = Integer.MAX_VALUE;

            for (IssueGroup classGroup : classes) {

                MaintainabilityFinding owner =
                        classGroup.findings().get(0);

                if (!sameFile(owner, method)
                        || !encloses(owner, method)
                        || !ownerMatches(owner, method)) {
                    continue;
                }

                int size =
                        owner.endLine() - owner.startLine();

                // Innermost affected class takes precedence
                // for nested Java class declarations.
                if (size < smallestRange
                        || (size == smallestRange
                        && bestParent != null
                        && classGroup.groupId()
                                .compareTo(bestParent.groupId()) < 0)) {

                    bestParent = classGroup;
                    smallestRange = size;
                }
            }

            if (bestParent != null) {
                parentByGroup.put(
                        candidate.groupId(),
                        bestParent.groupId()
                );
            }
        }

        Map<String, List<IssueGroup>> clusters =
                new LinkedHashMap<>();

        for (IssueGroup group : base) {

            String anchor = parentByGroup.getOrDefault(
                    group.groupId(),
                    group.groupId()
            );

            clusters.computeIfAbsent(
                    anchor,
                    ignored -> new ArrayList<>()
            ).add(group);
        }

        List<IssueGroup> output = new ArrayList<>();

        for (Map.Entry<String, List<IssueGroup>> entry
                : clusters.entrySet()) {

            List<IssueGroup> members = entry.getValue();

            if (members.size() == 1) {
                output.add(members.get(0));
                continue;
            }

            List<MaintainabilityFinding> merged =
                    members.stream()
                            .flatMap(group ->
                                    group.findings().stream())
                            .sorted(Comparator.comparing(
                                    MaintainabilityFinding::findingId))
                            .toList();

            output.add(new IssueGroup(
                    entry.getKey(),
                    "CLASS_METHOD_CONTEXT",
                    "Findings occur in an affected class "
                            + "and in methods structurally "
                            + "contained by that class. "
                            + "This is a contextual cluster, "
                            + "not a verified shared root cause.",
                    merged
            ));
        }

        output.sort(
                Comparator.comparing(IssueGroup::groupId)
        );

        return List.copyOf(output);
    }

    private boolean sameFile(
            MaintainabilityFinding first,
            MaintainabilityFinding second) {

        Path a = first.sourceFile()
                .toAbsolutePath().normalize();

        Path b = second.sourceFile()
                .toAbsolutePath().normalize();

        return a.equals(b);
    }

    private boolean encloses(
            MaintainabilityFinding owner,
            MaintainabilityFinding method) {

        return owner.startLine() <= method.startLine()
                && owner.endLine() >= method.endLine();
    }

    private boolean ownerMatches(
            MaintainabilityFinding owner,
            MaintainabilityFinding method) {

        String methodSymbol = method.symbolName();

        int separator = methodSymbol.lastIndexOf('.');

        if (separator < 1) {
            return false;
        }

        String methodOwner =
                methodSymbol.substring(0, separator);

        String className = owner.symbolName();

        // Exact name or matching qualified suffix.
        // The source-range check additionally restricts
        // the relationship to the enclosing declaration.
        return className.equals(methodOwner)
                || className.endsWith("." + methodOwner)
                || methodOwner.endsWith("." + className);
    }
}
