
package lk.sliit.codecleanliness.model;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MaintainabilityFindingTest {

    @Test
    void shouldCreateFindingWithEvidence() {

        MaintainabilityFinding finding =
                new MaintainabilityFinding(
                        "F-001",
                        MaintainabilityConcern.LONG_METHOD,
                        FindingScope.METHOD,
                        Path.of("src/Example.java"),
                        "Example.process()",
                        10,
                        80,
                        "LONG_METHOD_NCSS",
                        "Method exceeds the configured NCSS rule",
                        Map.of(
                                "ncss", "65",
                                "threshold", "50"
                        )
                );

        assertEquals(
                MaintainabilityConcern.LONG_METHOD,
                finding.concern()
        );

        assertEquals(FindingScope.METHOD, finding.scope());
        assertEquals(10, finding.startLine());
        assertEquals(80, finding.endLine());
        assertEquals("65", finding.evidence().get("ncss"));
    }

    @Test
    void shouldRejectInvalidLineRange() {

        assertThrows(
                IllegalArgumentException.class,
                () -> new MaintainabilityFinding(
                        "F-002",
                        MaintainabilityConcern.HIGH_COMPLEXITY,
                        FindingScope.METHOD,
                        Path.of("src/Example.java"),
                        "Example.run()",
                        50,
                        20,
                        "COMPLEXITY_RULE",
                        "Invalid location example",
                        Map.of("complexity", "15")
                )
        );
    }

    @Test
    void shouldRejectMissingConcern() {

        assertThrows(
                NullPointerException.class,
                () -> new MaintainabilityFinding(
                        "F-003",
                        null,
                        FindingScope.CLASS,
                        Path.of("src/Example.java"),
                        "Example",
                        1,
                        100,
                        "TEST_RULE",
                        "Example",
                        Map.of()
                )
        );
    }

    @Test
    void shouldProtectEvidenceFromModification() {

        Map<String, String> original = new HashMap<>();
        original.put("ncss", "65");

        MaintainabilityFinding finding =
                new MaintainabilityFinding(
                        "F-004",
                        MaintainabilityConcern.LONG_METHOD,
                        FindingScope.METHOD,
                        Path.of("src/Example.java"),
                        "Example.process()",
                        10,
                        80,
                        "LONG_METHOD_NCSS",
                        "Example finding",
                        original
                );

        original.put("ncss", "100");

        assertEquals(
                "65",
                finding.evidence().get("ncss")
        );

        assertThrows(
                UnsupportedOperationException.class,
                () -> finding.evidence().put("ncss", "200")
        );
    }
}
