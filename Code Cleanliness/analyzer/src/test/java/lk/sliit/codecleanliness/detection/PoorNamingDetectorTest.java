
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class PoorNamingDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect(String code, NamingDetectionConfig config)
            throws Exception {

        Files.writeString(root.resolve("Sample.java"), code);

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new PoorNamingDetector().detect(parsed, config);
    }

    private NamingDetectionConfig allChecks() {
        return new NamingDetectionConfig(true, true, true);
    }

    @Test
    void detectsTypeMethodAndFieldConventionIssues()
            throws Exception {

        var findings = detect(
                """
                class bad_type {
                    int bad_field;
                    void Bad_method() {}
                }
                """,
                allChecks()
        );

        assertEquals(3, findings.size());

        assertTrue(findings.stream().allMatch(
                finding -> finding.concern()
                        == MaintainabilityConcern.POOR_NAMING
        ));

        assertTrue(findings.stream().anyMatch(
                finding -> finding.scope() == FindingScope.CLASS
        ));

        assertTrue(findings.stream().anyMatch(
                finding -> finding.scope() == FindingScope.METHOD
        ));

        assertTrue(findings.stream().anyMatch(
                finding -> finding.scope() == FindingScope.FIELD
        ));
    }

    @Test
    void acceptsConventionalJavaNames() throws Exception {

        var findings = detect(
                """
                class CustomerService {
                    private int accountBalance;
                    static final int MAX_RETRIES = 3;
                    void calculateTotal() {}
                }
                """,
                allChecks()
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void canDisableFieldChecks() throws Exception {

        var findings = detect(
                """
                class CustomerService {
                    int bad_field;
                    void calculateTotal() {}
                }
                """,
                new NamingDetectionConfig(true, true, false)
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void preservesSourceEvidence() throws Exception {

        var findings = detect(
                """
                class CustomerService {
                    void Bad_method() {}
                }
                """,
                allChecks()
        );

        assertEquals(1, findings.size());

        var finding = findings.get(0);

        assertEquals(
                "Bad_method",
                finding.evidence().get("identifier")
        );
        assertEquals(
                "lowerCamelCase",
                finding.evidence().get("expectedConvention")
        );
        assertEquals(2, finding.startLine());
    }

    @Test
    void isDeterministic() throws Exception {

        Files.writeString(
                root.resolve("Sample.java"),
                """
                class bad_type {
                    int bad_field;
                    void Bad_method() {}
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new PoorNamingDetector();

        assertEquals(
                detector.detect(repository, allChecks()),
                detector.detect(repository, allChecks())
        );
    }
}
