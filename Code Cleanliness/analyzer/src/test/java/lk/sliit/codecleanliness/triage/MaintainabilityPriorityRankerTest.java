
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MaintainabilityPriorityRankerTest {

    private final MaintainabilityPriorityRanker ranker =
            new MaintainabilityPriorityRanker();

    private MaintainabilityFinding finding(
            String id,
            MaintainabilityConcern concern,
            String file,
            Map<String, String> evidence) {

        return new MaintainabilityFinding(
                id,
                concern,
                FindingScope.METHOD,
                Path.of(file),
                "Example.process()",
                10,
                30,
                "TEST_RULE",
                "Synthetic evidence for ranking test.",
                evidence
        );
    }

    private IssueGroup group(
            String id,
            MaintainabilityFinding... findings) {

        return new IssueGroup(
                id,
                "TEST_GROUP",
                "Synthetic grouping evidence.",
                List.of(findings)
        );
    }

    @Test
    void prioritizesHigherMeasuredExceedance() {

        IssueGroup moderate = group(
                "G-MODERATE",
                finding(
                        "F1",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/First.java",
                        Map.of(
                                "ncss", "12",
                                "configuredMaxNcss", "10"
                        )
                )
        );

        IssueGroup severe = group(
                "G-SEVERE",
                finding(
                        "F2",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/Second.java",
                        Map.of(
                                "ncss", "18",
                                "configuredMaxNcss", "10"
                        )
                )
        );

        List<RankedIssueGroup> ranked =
                ranker.rank(List.of(moderate, severe));

        assertEquals(
                "G-SEVERE",
                ranked.get(0).group().groupId()
        );

        assertEquals(0.8,
                ranked.get(0).exceedanceScore(),
                0.000001);
    }

    @Test
    void usesDistinctConcernsToBreakExceedanceTie() {

        MaintainabilityFinding first = finding(
                "F1",
                MaintainabilityConcern.LONG_METHOD,
                "src/Example.java",
                Map.of(
                        "ncss", "15",
                        "configuredMaxNcss", "10"
                )
        );

        MaintainabilityFinding second = finding(
                "F2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                "src/Example.java",
                Map.of(
                        "cyclomaticComplexity", "6",
                        "configuredMaxComplexity", "4"
                )
        );

        IssueGroup combined =
                group("G-COMBINED", first, second);

        IssueGroup single =
                group(
                        "G-SINGLE",
                        finding(
                                "F3",
                                MaintainabilityConcern.LONG_METHOD,
                                "src/Other.java",
                                Map.of(
                                        "ncss", "15",
                                        "configuredMaxNcss", "10"
                                )
                        )
                );

        List<RankedIssueGroup> ranked =
                ranker.rank(List.of(single, combined));

        assertEquals(
                "G-COMBINED",
                ranked.get(0).group().groupId()
        );

        assertEquals(
                2,
                ranked.get(0).distinctConcernCount()
        );
    }

    @Test
    void calculatesSpreadAcrossMultipleFiles() {

        IssueGroup crossFile = group(
                "G-CROSS",
                finding(
                        "F1",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/First.java",
                        Map.of(
                                "ncss", "12",
                                "configuredMaxNcss", "10"
                        )
                ),
                finding(
                        "F2",
                        MaintainabilityConcern.HIGH_COMPLEXITY,
                        "src/Second.java",
                        Map.of(
                                "cyclomaticComplexity", "5",
                                "configuredMaxComplexity", "4"
                        )
                )
        );

        RankedIssueGroup result =
                ranker.rank(List.of(crossFile)).get(0);

        assertEquals(2, result.affectedFileCount());
    }

    @Test
    void doesNotInventScoresForUnsupportedEvidence() {

        IssueGroup unsupported = group(
                "G-UNKNOWN",
                finding(
                        "F1",
                        MaintainabilityConcern.SRP_RISK,
                        "src/Example.java",
                        Map.of("note", "unverified")
                )
        );

        RankedIssueGroup result =
                ranker.rank(List.of(unsupported)).get(0);

        assertEquals(
                0.0,
                result.exceedanceScore()
        );

        assertEquals(
                0,
                result.supportedFindingCount()
        );
    }

    @Test
    void producesDeterministicRankingRegardlessOfInputOrder() {

        IssueGroup first = group(
                "G-A",
                finding(
                        "F1",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/A.java",
                        Map.of(
                                "ncss", "12",
                                "configuredMaxNcss", "10"
                        )
                )
        );

        IssueGroup second = group(
                "G-B",
                finding(
                        "F2",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/B.java",
                        Map.of(
                                "ncss", "12",
                                "configuredMaxNcss", "10"
                        )
                )
        );

        assertEquals(
                ranker.rank(List.of(first, second)),
                ranker.rank(List.of(second, first))
        );
    }

    @Test
    void rejectsDuplicateGroupIdentifiers() {

        IssueGroup first = group(
                "G-SAME",
                finding(
                        "F1",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/A.java",
                        Map.of()
                )
        );

        IssueGroup second = group(
                "G-SAME",
                finding(
                        "F2",
                        MaintainabilityConcern.LONG_METHOD,
                        "src/B.java",
                        Map.of()
                )
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> ranker.rank(List.of(first, second))
        );
    }


    
    @Test
    void recognizesCrossFileDuplicationAsStructuralEvidence() {

        IssueGroup crossFileDuplicate = group(
                "G-DUPLICATE",
                finding(
                        "D1",
                        MaintainabilityConcern.DUPLICATED_LOGIC,
                        "src/First.java",
                        Map.of(
                                "fingerprint", "abc123",
                                "measurement",
                                "exact_normalized_method_body",
                                "normalizedTokenCount", "50",
                                "occurrenceCount", "2",
                                "affectedFileCount", "2"
                        )
                ),
                finding(
                        "D2",
                        MaintainabilityConcern.DUPLICATED_LOGIC,
                        "src/Second.java",
                        Map.of(
                                "fingerprint", "abc123",
                                "measurement",
                                "exact_normalized_method_body",
                                "normalizedTokenCount", "50",
                                "occurrenceCount", "2",
                                "affectedFileCount", "2"
                        )
                )
        );

        RankedIssueGroup result =
                ranker.rank(List.of(crossFileDuplicate))
                        .get(0);

        assertEquals(2, result.affectedFileCount());

        assertEquals(
                2,
                result.supportedFindingCount(),
                "Both duplicated logic findings have "
                        + "supported structural evidence"
        );

        assertEquals(
                0.0,
                result.exceedanceScore(),
                0.000001,
                "Structural duplication evidence must not "
                        + "be converted into a fabricated "
                        + "threshold exceedance"
        );
    }

}
