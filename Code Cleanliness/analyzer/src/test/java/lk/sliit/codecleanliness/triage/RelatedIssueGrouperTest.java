
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class RelatedIssueGrouperTest {

    private final RelatedIssueGrouper grouper =
            new RelatedIssueGrouper();

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
                Path.of(file).toAbsolutePath().normalize(),
                symbol,
                start,
                end,
                "TEST_RULE",
                "Synthetic test finding.",
                Map.of("source", "synthetic_test")
        );
    }

    @Test
    void groupsDifferentConcernsOnSameMethod() {

        MaintainabilityFinding longMethod = finding(
                "F1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/Example.java",
                "Example.process()",
                10,
                30
        );

        MaintainabilityFinding complex = finding(
                "F2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                FindingScope.METHOD,
                "src/Example.java",
                "Example.process()",
                10,
                30
        );

        List<IssueGroup> groups =
                grouper.group(List.of(complex, longMethod));

        assertEquals(1, groups.size());
        assertEquals(2, groups.get(0).findingCount());
        assertEquals(
                "SAME_METHOD",
                groups.get(0).relationshipType()
        );
    }

    @Test
    void groupsDifferentConcernsOnSameClass() {

        MaintainabilityFinding largeClass = finding(
                "F1",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/Example.java",
                "example.Example",
                1,
                100
        );

        MaintainabilityFinding weakCohesion = finding(
                "F2",
                MaintainabilityConcern.WEAK_COHESION,
                FindingScope.CLASS,
                "src/Example.java",
                "example.Example",
                1,
                100
        );

        List<IssueGroup> groups =
                grouper.group(
                        List.of(weakCohesion, largeClass)
                );

        assertEquals(1, groups.size());
        assertEquals(2, groups.get(0).findingCount());
        assertEquals(
                "SAME_CLASS",
                groups.get(0).relationshipType()
        );
    }

    @Test
    void doesNotGroupSameNamedMethodsInDifferentFiles() {

        MaintainabilityFinding first = finding(
                "F1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/First.java",
                "run()",
                5,
                20
        );

        MaintainabilityFinding second = finding(
                "F2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                FindingScope.METHOD,
                "src/Second.java",
                "run()",
                5,
                20
        );

        List<IssueGroup> groups =
                grouper.group(List.of(first, second));

        assertEquals(2, groups.size());

        assertTrue(
                groups.stream()
                        .noneMatch(
                                IssueGroup::containsRelatedFindings
                        )
        );
    }

    @Test
    void keepsUnsupportedScopesSeparate() {

        MaintainabilityFinding first = finding(
                "F1",
                MaintainabilityConcern.POOR_NAMING,
                FindingScope.FIELD,
                "src/Example.java",
                "bad_name",
                8,
                8
        );

        MaintainabilityFinding second = finding(
                "F2",
                MaintainabilityConcern.POOR_NAMING,
                FindingScope.FIELD,
                "src/Example.java",
                "bad_name",
                8,
                8
        );

        List<IssueGroup> groups =
                grouper.group(List.of(first, second));

        assertEquals(2, groups.size());
    }

    @Test
    void maintainsStableOutputRegardlessOfInputOrder() {

        MaintainabilityFinding first = finding(
                "F1",
                MaintainabilityConcern.LONG_METHOD,
                FindingScope.METHOD,
                "src/Example.java",
                "run()",
                5,
                20
        );

        MaintainabilityFinding second = finding(
                "F2",
                MaintainabilityConcern.HIGH_COMPLEXITY,
                FindingScope.METHOD,
                "src/Example.java",
                "run()",
                5,
                20
        );

        MaintainabilityFinding third = finding(
                "F3",
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                "src/Example.java",
                "Example",
                1,
                50
        );

        List<IssueGroup> firstRun =
                grouper.group(
                        List.of(third, first, second)
                );

        List<IssueGroup> secondRun =
                grouper.group(
                        List.of(second, third, first)
                );

        assertEquals(firstRun, secondRun);
    }
}
