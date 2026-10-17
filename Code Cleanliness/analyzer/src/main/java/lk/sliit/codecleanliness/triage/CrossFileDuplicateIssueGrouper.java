
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/**
 * Evidence-based cross-file grouping of duplicated logic.
 *
 * Uses fingerprints produced by DuplicatedLogicDetector.
 *
 * A cross-file group requires:
 * - DUPLICATED_LOGIC findings;
 * - the exact normalized-method-body measurement;
 * - identical nonblank fingerprints;
 * - occurrences in at least two different source files.
 *
 * Existing context groups are preserved where possible.
 * Selected duplicate findings are removed from their old
 * groups before being placed in cross-file groups.
 *
 * Every original finding must occur exactly once.
 */
public class CrossFileDuplicateIssueGrouper {

    public List<IssueGroup> group(List<IssueGroup> input) {

        Objects.requireNonNull(input, "Issue groups are required");

        Map<String, List<MaintainabilityFinding>> byFingerprint =
                new TreeMap<>();

        Map<String, MaintainabilityFinding> originals =
                new HashMap<>();

        for (IssueGroup group : input) {
            Objects.requireNonNull(group);

            for (MaintainabilityFinding finding : group.findings()) {

                if (originals.putIfAbsent(
                        finding.findingId(), finding) != null) {

                    throw new IllegalArgumentException(
                            "Finding appears in multiple input groups: "
                                    + finding.findingId()
                    );
                }

                String fingerprint = eligibleFingerprint(finding);

                if (fingerprint != null) {
                    byFingerprint.computeIfAbsent(
                            fingerprint,
                            ignored -> new ArrayList<>()
                    ).add(finding);
                }
            }
        }

        Map<String, List<MaintainabilityFinding>> crossFile =
                new LinkedHashMap<>();

        Set<String> relocatedIds = new HashSet<>();

        for (Map.Entry<String, List<MaintainabilityFinding>> entry
                : byFingerprint.entrySet()) {

            Set<Path> distinctFiles = new HashSet<>();

            for (MaintainabilityFinding finding : entry.getValue()) {
                distinctFiles.add(
                        finding.sourceFile()
                                .toAbsolutePath()
                                .normalize()
                );
            }

            if (distinctFiles.size() < 2) {
                continue;
            }

            List<MaintainabilityFinding> members =
                    entry.getValue().stream()
                            .sorted(Comparator.comparing(
                                    MaintainabilityFinding::findingId))
                            .toList();

            crossFile.put(entry.getKey(), members);

            for (MaintainabilityFinding finding : members) {
                relocatedIds.add(finding.findingId());
            }
        }

        // No cross-file evidence: preserve the existing result.
        if (crossFile.isEmpty()) {
            return List.copyOf(input);
        }

        List<IssueGroup> output = new ArrayList<>();

        // Preserve or safely reconstruct original groups after
        // extracting qualifying cross-file duplicate findings.
        for (IssueGroup original : input) {

            List<MaintainabilityFinding> remaining =
                    original.findings().stream()
                            .filter(finding ->
                                    !relocatedIds.contains(
                                            finding.findingId()))
                            .toList();

            if (remaining.isEmpty()) {
                continue;
            }

            if (remaining.size() == original.findingCount()) {
                output.add(original);
                continue;
            }

            if (remaining.size() == 1) {
                output.add(new IssueGroup(
                        original.groupId(),
                        "SINGLE_FINDING",
                        "The original contextual group was split "
                                + "to associate duplicated logic "
                                + "across files. This remaining "
                                + "finding is retained separately.",
                        remaining
                ));
            } else {
                output.add(new IssueGroup(
                        original.groupId(),
                        "RETAINED_CONTEXT",
                        "These findings remain from an existing "
                                + "contextual group after cross-file "
                                + "duplicated logic was extracted. "
                                + "Their shared root cause has not "
                                + "been established.",
                        remaining
                ));
            }
        }

        for (Map.Entry<String, List<MaintainabilityFinding>> entry
                : crossFile.entrySet()) {

            String fingerprint = entry.getKey();
            List<MaintainabilityFinding> members =
                    entry.getValue();

            output.add(new IssueGroup(
                    "CROSS_FILE_DUPLICATED_LOGIC:" + fingerprint,
                    "CROSS_FILE_DUPLICATED_LOGIC",
                    "Findings in multiple Java source files have "
                            + "the same normalized method-body "
                            + "fingerprint. They are grouped as "
                            + "related duplication candidates, "
                            + "not a verified common root cause "
                            + "or mandatory refactoring.",
                    members
            ));
        }

        output.sort(Comparator.comparing(IssueGroup::groupId));

        // Verify that grouping remains a partition of the
        // original findings: no missing or repeated findings.
        Map<String, MaintainabilityFinding> produced =
                new HashMap<>();

        for (IssueGroup group : output) {
            for (MaintainabilityFinding finding : group.findings()) {
                if (produced.putIfAbsent(
                        finding.findingId(), finding) != null) {
                    throw new IllegalStateException(
                            "Duplicate grouped finding: "
                                    + finding.findingId()
                    );
                }
            }
        }

        if (!originals.equals(produced)) {
            throw new IllegalStateException(
                    "Cross-file grouping changed finding coverage"
            );
        }

        return List.copyOf(output);
    }

    private String eligibleFingerprint(
            MaintainabilityFinding finding) {

        if (finding.concern()
                != MaintainabilityConcern.DUPLICATED_LOGIC) {
            return null;
        }

        if (!"exact_normalized_method_body".equals(
                finding.evidence().get("measurement"))) {
            return null;
        }

        String fingerprint =
                finding.evidence().get("fingerprint");

        if (fingerprint == null || fingerprint.isBlank()) {
            return null;
        }

        return fingerprint;
    }
}
