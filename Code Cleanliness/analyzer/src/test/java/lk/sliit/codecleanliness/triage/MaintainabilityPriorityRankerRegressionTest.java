package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MaintainabilityPriorityRankerRegressionTest {

    private final MaintainabilityPriorityRanker ranker =
            new MaintainabilityPriorityRanker();

    private MaintainabilityFinding finding(
            String id,
            MaintainabilityConcern concern,
            String file,
            Map<String, String> evidence) {

        return new MaintainabilityFinding(
                id, concern, FindingScope.METHOD,
                Path.of(file), "Example.process()",
                10, 30, "TEST_RULE",
                "Controlled ranking regression evidence.",
                evidence
        );
    }

    private IssueGroup group(
            String id, MaintainabilityFinding... findings) {

        return new IssueGroup(
                id, "CONTROLLED_TEST",
                "Controlled grouping for ranking validation.",
                List.of(findings)
        );
    }

    private MaintainabilityFinding longMethod(
            String id, String file, int ncss) {

        return finding(
                id,
                MaintainabilityConcern.LONG_METHOD,
                file,
                Map.of(
                        "ncss", Integer.toString(ncss),
                        "configuredMaxNcss", "10"
                )
        );
    }

    @Test
    void documentsScoreSaturationAtTwiceBoundary() {
        var moderate = group(
                "G-MODERATE",
                longMethod("F1", "src/A.java", 15)
        );
        var severe = group(
                "G-SEVERE",
                longMethod("F2", "src/B.java", 20)
        );
        var extreme = group(
                "G-EXTREME",
                longMethod("F3", "src/C.java", 200)
        );

        var ranked = ranker.rank(
                List.of(moderate, severe, extreme)
        );

        var scores = ranked.stream()
                .collect(java.util.stream.Collectors.toMap(
                        r -> r.group().groupId(),
                        RankedIssueGroup::exceedanceScore
                ));

        assertEquals(0.5, scores.get("G-MODERATE"), 1e-9);
        assertEquals(1.0, scores.get("G-SEVERE"), 1e-9);
        assertEquals(1.0, scores.get("G-EXTREME"), 1e-9);
    }

    @Test
    void distinctConcernsBreakSaturatedScoreTie() {
        var single = group(
                "G-SINGLE",
                longMethod("F1", "src/A.java", 200)
        );

        var combined = group(
                "G-COMBINED",
                longMethod("F2", "src/B.java", 20),
                finding(
                        "F3",
                        MaintainabilityConcern.HIGH_COMPLEXITY,
                        "src/B.java",
                        Map.of(
                                "cyclomaticComplexity", "8",
                                "configuredMaxComplexity", "4"
                        )
                )
        );

        var ranked = ranker.rank(List.of(single, combined));

        assertEquals(
                "G-COMBINED",
                ranked.get(0).group().groupId()
        );
        assertEquals(1.0, ranked.get(0).exceedanceScore());
        assertEquals(2, ranked.get(0).distinctConcernCount());
    }

    @Test
    void supportedFindingsBreakRemainingTies() {
        var oneFinding = group(
                "G-ONE",
                longMethod("F1", "src/A.java", 20)
        );

        var twoFindings = group(
                "G-TWO",
                longMethod("F2", "src/B.java", 20),
                longMethod("F3", "src/B.java", 25)
        );

        var ranked = ranker.rank(
                List.of(oneFinding, twoFindings)
        );

        assertEquals(
                "G-TWO",
                ranked.get(0).group().groupId()
        );
        assertEquals(2, ranked.get(0).supportedFindingCount());
    }

    @Test
    void usesMaximumExceedanceWithinGroup() {
        var mixed = group(
                "G-MIXED",
                longMethod("F1", "src/A.java", 12),
                longMethod("F2", "src/A.java", 18)
        );

        var ranked = ranker.rank(List.of(mixed));

        assertEquals(1, ranked.size());
        assertEquals(
                0.8,
                ranked.get(0).exceedanceScore(),
                1e-9
        );
    }
}
