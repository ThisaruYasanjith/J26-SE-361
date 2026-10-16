
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Deterministic preliminary prioritization.
 *
 * Ranking strategy:
 * 1. Maximum supported normalized boundary exceedance
 * 2. Number of distinct maintainability concerns
 * 3. Number of affected source files
 * 4. Number of findings with usable metric evidence
 * 5. Stable group identifier
 *
 * No empirically calibrated weights are claimed.
 */
public class MaintainabilityPriorityRanker {

    public List<RankedIssueGroup> rank(
            List<IssueGroup> groups) {

        Objects.requireNonNull(groups, "Issue groups are required");

        List<Factors> candidates = new ArrayList<>();

        Set<String> groupIds = new java.util.HashSet<>();

        for (IssueGroup group : groups) {
            Objects.requireNonNull(group, "Issue group is required");

            if (!groupIds.add(group.groupId())) {
                throw new IllegalArgumentException(
                        "Duplicate group ID: " + group.groupId()
                );
            }

            candidates.add(calculateFactors(group));
        }

        candidates.sort(
                Comparator
                        .comparingDouble(
                                Factors::exceedanceScore
                        ).reversed()
                        .thenComparing(
                                Comparator.comparingInt(
                                        Factors::distinctConcerns
                                ).reversed()
                        )
                        .thenComparing(
                                Comparator.comparingInt(
                                        Factors::affectedFiles
                                ).reversed()
                        )
                        .thenComparing(
                                Comparator.comparingInt(
                                        Factors::supportedFindings
                                ).reversed()
                        )
                        .thenComparing(
                                factors -> factors.group().groupId()
                        )
        );

        List<RankedIssueGroup> ranked = new ArrayList<>();

        for (int i = 0; i < candidates.size(); i++) {
            Factors factors = candidates.get(i);

            String explanation =
                    "Provisional lexicographic ranking: "
                    + "maximum normalized boundary exceedance="
                    + factors.exceedanceScore()
                    + ", distinct concerns="
                    + factors.distinctConcerns()
                    + ", affected source files="
                    + factors.affectedFiles()
                    + ", findings with usable metric evidence="
                    + factors.supportedFindings()
                    + ". These factors are not calibrated "
                    + "against maintenance effort.";

            ranked.add(new RankedIssueGroup(
                    i + 1,
                    factors.group(),
                    factors.exceedanceScore(),
                    factors.distinctConcerns(),
                    factors.affectedFiles(),
                    factors.supportedFindings(),
                    explanation
            ));
        }

        return List.copyOf(ranked);
    }

    private Factors calculateFactors(IssueGroup group) {

        double highestExceedance = 0.0;
        int supported = 0;

        for (MaintainabilityFinding finding : group.findings()) {
            Double value = evidenceExceedance(finding);

            if (value != null) {
                highestExceedance = Math.max(
                        highestExceedance,
                        value
                );
                supported++;
            }
        }

        int concerns = (int) group.findings()
                .stream()
                .map(MaintainabilityFinding::concern)
                .distinct()
                .count();

        int files = (int) group.findings()
                .stream()
                .map(finding -> finding.sourceFile()
                        .toAbsolutePath()
                        .normalize())
                .distinct()
                .count();

        return new Factors(
                group,
                highestExceedance,
                concerns,
                files,
                supported
        );
    }

    /**
     * Returns null if no supported numeric metric/boundary
     * pair can be read. A numeric value of zero is different
     * from missing evidence.
     */
    private Double evidenceExceedance(
            MaintainabilityFinding finding) {

        Map<String, String> evidence = finding.evidence();

        List<Double> values = new ArrayList<>();

        MaintainabilityConcern concern = finding.concern();

        switch (concern) {

            case LONG_METHOD -> addUpper(
                    values, evidence,
                    "ncss", "configuredMaxNcss"
            );

            case HIGH_COMPLEXITY -> addUpper(
                    values, evidence,
                    "cyclomaticComplexity",
                    "configuredMaxComplexity"
            );

            case LARGE_CLASS -> {
                addUpper(
                        values, evidence,
                        "classNcss", "maxClassNcss"
                );
                addUpper(
                        values, evidence,
                        "methodCount", "maxMethodCount"
                );
                addUpper(
                        values, evidence,
                        "fieldCount", "maxFieldCount"
                );
            }

            case WEAK_COHESION -> {
                addLower(
                        values, evidence,
                        "tcc", "configuredMaxTcc"
                );
                addUpper(
                        values, evidence,
                        "lcom4", "configuredMinLcom4"
                );
            }

            case GOD_CLASS -> {
                addUpper(
                        values, evidence,
                        "wmc", "configuredMinWmc"
                );
                addUpper(
                        values, evidence,
                        "atfd", "configuredMinAtfd"
                );
                addLower(
                        values, evidence,
                        "tcc", "configuredMaxTcc"
                );
            }

            default -> {
                // Unimplemented concerns receive no
                // invented exceedance evidence.
            }
        }

        if (values.isEmpty()) {
            return null;
        }

        return values.stream()
                .mapToDouble(Double::doubleValue)
                .max()
                .orElse(0.0);
    }

    private void addUpper(
            List<Double> values,
            Map<String, String> evidence,
            String actualKey,
            String boundaryKey) {

        Double actual = number(evidence, actualKey);
        Double boundary = number(evidence, boundaryKey);

        if (actual == null
                || boundary == null
                || actual < 0.0
                || boundary <= 0.0) {
            return;
        }

        double ratio = actual / boundary - 1.0;

        values.add(clamp(ratio));
    }

    private void addLower(
            List<Double> values,
            Map<String, String> evidence,
            String actualKey,
            String boundaryKey) {

        Double actual = number(evidence, actualKey);
        Double boundary = number(evidence, boundaryKey);

        if (actual == null
                || boundary == null
                || actual < 0.0
                || boundary <= 0.0) {
            return;
        }

        double ratio = (boundary - actual) / boundary;

        values.add(clamp(ratio));
    }

    private Double number(
            Map<String, String> evidence,
            String key) {

        String raw = evidence.get(key);

        if (raw == null || raw.isBlank()) {
            return null;
        }

        try {
            double value = Double.parseDouble(raw);

            return Double.isFinite(value) ? value : null;

        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private double clamp(double value) {
        return Math.min(1.0, Math.max(0.0, value));
    }

    private record Factors(
            IssueGroup group,
            double exceedanceScore,
            int distinctConcerns,
            int affectedFiles,
            int supportedFindings
    ) {}
}
