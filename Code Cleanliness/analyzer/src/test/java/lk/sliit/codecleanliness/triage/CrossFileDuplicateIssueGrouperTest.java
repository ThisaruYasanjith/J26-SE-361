
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class CrossFileDuplicateIssueGrouperTest {

    private MaintainabilityFinding duplicate(
            String id, String file, String fingerprint) {

        return new MaintainabilityFinding(
                id,
                MaintainabilityConcern.DUPLICATED_LOGIC,
                FindingScope.METHOD,
                Path.of(file),
                "Example.process()",
                5,
                5,
                "EXACT_NORMALIZED_DUPLICATION",
                "Duplicated normalized method body.",
                Map.of(
                        "fingerprint", fingerprint,
                        "measurement",
                        "exact_normalized_method_body"
                )
        );
    }

    private MaintainabilityFinding classFinding(
            String id, String file) {

        return new MaintainabilityFinding(
                id,
                MaintainabilityConcern.LARGE_CLASS,
                FindingScope.CLASS,
                Path.of(file),
                "Example",
                1,
                30,
                "LARGE_CLASS_TEST",
                "Class size exceeds a test threshold.",
                Map.of()
        );
    }

    private IssueGroup single(MaintainabilityFinding finding) {
        return new IssueGroup(
                "GROUP:" + finding.findingId(),
                "SINGLE_FINDING",
                "No established grouping relationship.",
                List.of(finding)
        );
    }

    @Test
    void groupsMatchingFingerprintsAcrossFiles() {

        var first = duplicate("D1", "A.java", "fingerprint-001");
        var second = duplicate("D2", "B.java", "fingerprint-001");
        var third = duplicate("D3", "C.java", "fingerprint-001");

        var result = new CrossFileDuplicateIssueGrouper()
                .group(List.of(
                        single(first),
                        single(second),
                        single(third)
                ));

        assertEquals(1, result.size());

        assertEquals(
                "CROSS_FILE_DUPLICATED_LOGIC",
                result.get(0).relationshipType()
        );

        assertEquals(3, result.get(0).findingCount());
    }

    @Test
    void doesNotGroupOccurrencesFromOnlyOneFile() {

        var first = duplicate("D1", "A.java", "same");
        var second = duplicate("D2", "A.java", "same");

        var input = List.of(single(first), single(second));

        var result = new CrossFileDuplicateIssueGrouper()
                .group(input);

        assertEquals(input, result);
    }

    @Test
    void doesNotMergeDifferentFingerprints() {

        var first = duplicate("D1", "A.java", "one");
        var second = duplicate("D2", "B.java", "two");

        var input = List.of(single(first), single(second));

        assertEquals(
                input,
                new CrossFileDuplicateIssueGrouper().group(input)
        );
    }

    @Test
    void preservesOtherFindingsWhenSplittingContextGroup() {

        var largeClass = classFinding("C1", "A.java");

        var duplicateA =
                duplicate("D1", "A.java", "shared-fingerprint");

        var duplicateB =
                duplicate("D2", "B.java", "shared-fingerprint");

        var context = new IssueGroup(
                "GROUP:C1",
                "CLASS_METHOD_CONTEXT",
                "Existing class-method contextual relationship.",
                List.of(largeClass, duplicateA)
        );

        var result = new CrossFileDuplicateIssueGrouper()
                .group(List.of(context, single(duplicateB)));

        assertEquals(2, result.size());

        var crossFile = result.stream()
                .filter(group ->
                        group.relationshipType().equals(
                                "CROSS_FILE_DUPLICATED_LOGIC"))
                .findFirst()
                .orElseThrow();

        assertEquals(2, crossFile.findingCount());

        Set<String> ids = result.stream()
                .flatMap(group -> group.findings().stream())
                .map(MaintainabilityFinding::findingId)
                .collect(Collectors.toSet());

        assertEquals(Set.of("C1", "D1", "D2"), ids);

        assertEquals(
                3,
                result.stream()
                        .mapToInt(IssueGroup::findingCount)
                        .sum()
        );
    }

    @Test
    void resultsAreDeterministic() {

        var input = List.of(
                single(duplicate(
                        "D3", "C.java", "shared")),
                single(duplicate(
                        "D1", "A.java", "shared")),
                single(duplicate(
                        "D2", "B.java", "shared"))
        );

        var grouper = new CrossFileDuplicateIssueGrouper();

        assertEquals(
                grouper.group(input),
                grouper.group(input)
        );
    }
}
