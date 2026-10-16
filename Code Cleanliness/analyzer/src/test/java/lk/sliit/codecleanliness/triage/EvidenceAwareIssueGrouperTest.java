
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EvidenceAwareIssueGrouperTest {

    private final EvidenceAwareIssueGrouper grouper =
            new EvidenceAwareIssueGrouper();

    private MaintainabilityFinding finding(
            String id,
            MaintainabilityConcern concern,
            FindingScope scope,
            String file,
            String symbol,
            int start,
            int end) {

        return new MaintainabilityFinding(
                id,
                concern,
                scope,
                Path.of(file),
                symbol,
                start,
                end,
                "TEST_RULE",
                "Synthetic maintainability finding.",
                Map.of()
        );
    }

    @Test
    void groupsMethodFindingWithAffectedEnclosingClass() {

        MaintainabilityFinding classFinding = finding(
                "CLASS-1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/Service.java",
                "example.Service",
                1, 100
        );

        MaintainabilityFinding methodFinding = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/Service.java",
                "Service.process()",
                20, 40
        );

        List<IssueGroup> groups =
                grouper.group(List.of(
                        methodFinding, classFinding));

        assertEquals(1, groups.size());
        assertEquals(
                "CLASS_METHOD_CONTEXT",
                groups.get(0).relationshipType()
        );
        assertEquals(2, groups.get(0).findingCount());
    }

    @Test
    void doesNotMergeFindingsFromDifferentFiles() {

        MaintainabilityFinding classFinding = finding(
                "CLASS-1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/A.java",
                "example.Service",
                1, 100
        );

        MaintainabilityFinding methodFinding = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/B.java",
                "Service.process()",
                20, 40
        );

        assertEquals(
                2,
                grouper.group(List.of(
                        classFinding, methodFinding)).size()
        );
    }

    @Test
    void doesNotMergeUnrelatedMethodOutsideClassRange() {

        MaintainabilityFinding classFinding = finding(
                "CLASS-1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/A.java",
                "example.Service",
                1, 50
        );

        MaintainabilityFinding methodFinding = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/A.java",
                "Service.process()",
                60, 80
        );

        assertEquals(
                2,
                grouper.group(List.of(
                        classFinding, methodFinding)).size()
        );
    }

    @Test
    void doesNotMergeWhenOwnerSymbolDoesNotMatch() {

        MaintainabilityFinding classFinding = finding(
                "CLASS-1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/A.java",
                "example.Service",
                1, 100
        );

        MaintainabilityFinding methodFinding = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/A.java",
                "Other.process()",
                20, 40
        );

        assertEquals(
                2,
                grouper.group(List.of(
                        classFinding, methodFinding)).size()
        );
    }

    @Test
    void preservesAllFindingsWithoutDuplication() {

        MaintainabilityFinding classFinding = finding(
                "CLASS-1",
                MaintainabilityConcern.WEAK_COHESION,
                FindingScope.CLASS,
                "src/Service.java",
                "example.Service",
                1, 100
        );

        MaintainabilityFinding first = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/Service.java",
                "Service.first()",
                10, 30
        );

        MaintainabilityFinding second = finding(
                "METHOD-2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                FindingScope.METHOD,
                "src/Service.java",
                "Service.second()",
                40, 60
        );

        List<IssueGroup> groups =
                grouper.group(List.of(
                        classFinding, first, second));

        assertEquals(1, groups.size());
        assertEquals(3, groups.get(0).findingCount());

        assertEquals(
                3,
                groups.stream()
                        .flatMap(group ->
                                group.findings().stream())
                        .map(MaintainabilityFinding::findingId)
                        .distinct()
                        .count()
        );
    }

    @Test
    void retainsExactLocationGroupingWithoutClassFinding() {

        MaintainabilityFinding first = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/A.java",
                "Service.process()",
                20, 40
        );

        MaintainabilityFinding second = finding(
                "METHOD-2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                FindingScope.METHOD,
                "src/A.java",
                "Service.process()",
                20, 40
        );

        List<IssueGroup> groups =
                grouper.group(List.of(first, second));

        assertEquals(1, groups.size());
        assertEquals(
                "SAME_METHOD",
                groups.get(0).relationshipType()
        );
    }

    @Test
    void rankingInputRemainsDeterministic() {

        MaintainabilityFinding first = finding(
                "CLASS-1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/Service.java",
                "example.Service",
                1, 100
        );

        MaintainabilityFinding second = finding(
                "METHOD-1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/Service.java",
                "Service.process()",
                20, 40
        );

        assertEquals(
                grouper.group(List.of(first, second)),
                grouper.group(List.of(second, first))
        );
    }
}
