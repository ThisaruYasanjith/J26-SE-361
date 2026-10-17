
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SrpRiskDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect(String source) throws Exception {

        Files.writeString(
                root.resolve("Example.java"), source);

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new SrpRiskDetector().detect(repository);
    }

    @Test
    void identifiesSeparateMethodFieldGroups()
            throws Exception {

        var findings = detect(
                """
                class CombinedManager {
                    private int customerCount;
                    private int invoiceCount;

                    void addCustomer() {
                        customerCount++;
                    }

                    void removeCustomer() {
                        customerCount--;
                    }

                    void addInvoice() {
                        invoiceCount++;
                    }

                    void removeInvoice() {
                        invoiceCount--;
                    }
                }
                """
        );

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.SRP_RISK,
                findings.get(0).concern()
        );

        assertEquals(
                "2",
                findings.get(0).evidence()
                        .get("qualifyingGroupCount")
        );
    }

    @Test
    void acceptsMethodsSharingTheSameField()
            throws Exception {

        var findings = detect(
                """
                class Counter {
                    private int value;

                    void increment() { value++; }
                    void decrement() { value--; }
                    void reset() { value = 0; }
                    int read() { return value; }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void avoidsTinyClasses() throws Exception {

        var findings = detect(
                """
                class SmallClass {
                    int first;
                    int second;

                    void changeFirst() { first++; }
                    void changeSecond() { second++; }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void resultsAreDeterministic() throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                class CombinedManager {
                    int left;
                    int right;

                    void leftA() { left++; }
                    void leftB() { left--; }
                    void rightA() { right++; }
                    void rightB() { right--; }
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new SrpRiskDetector();

        assertEquals(
                detector.detect(repository),
                detector.detect(repository)
        );
    }
}
