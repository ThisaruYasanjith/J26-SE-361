
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class RepositoryAnalyzerIntegrationTest {

    @TempDir
    Path tempDir;

    private RepositoryDetectionConfig config() {

        // Controlled values for synthetic integration tests.
        // These are NOT validated production thresholds.
        return new RepositoryDetectionConfig(
                new MethodDetectionThresholds(1, 1),
                new ClassDetectionThresholds(1, 1, 1),
                new CohesionDetectionThresholds(0.5, 2),
                new GodClassDetectionThresholds(4, 2, 0.5)
        );
    }

    private void write(
            String filename,
            String source) throws IOException {

        Path directory = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                directory.resolve(filename),
                source
        );
    }

    private void createSampleRepository()
            throws IOException {

        write("Sample.java", """
                package example;

                class Customer {
                    int balance;
                }

                class Order {
                    int quantity;
                }

                public class Sample {

                    Customer customer = new Customer();
                    Order order = new Order();

                    void processCustomer(boolean active) {
                        if (active) {
                            customer.balance++;
                        }
                    }

                    void processOrder(boolean valid) {
                        if (valid) {
                            order.quantity++;
                        }
                    }
                }
                """);

        write("Another.java", """
                package example;

                public class Another {

                    void simple() {
                        int value = 1;
                    }
                }
                """);
    }

    @Test
    void combinesFiveMaintainabilityConcernsAcrossRepository()
            throws IOException {

        createSampleRepository();

        RepositoryAnalysisResult result =
                new RepositoryAnalyzer().analyze(
                        tempDir,
                        config()
                );

        assertEquals(2, result.parsedFiles());
        assertEquals(0, result.failedFiles());

        Set<MaintainabilityConcern> concerns =
                result.findings().stream()
                        .map(finding -> finding.concern())
                        .collect(Collectors.toSet());

        assertTrue(
                concerns.contains(
                        MaintainabilityConcern.LONG_METHOD
                ),
                "Expected a Long Method finding"
        );

        assertTrue(
                concerns.contains(
                        MaintainabilityConcern.HIGH_COMPLEXITY
                ),
                "Expected a High Complexity finding"
        );

        assertTrue(
                concerns.contains(
                        MaintainabilityConcern.LARGE_CLASS
                ),
                "Expected a Large Class finding"
        );

        assertTrue(
                concerns.contains(
                        MaintainabilityConcern.WEAK_COHESION
                ),
                "Expected a Weak Cohesion finding"
        );

        assertTrue(
                concerns.contains(
                        MaintainabilityConcern.GOD_CLASS
                ),
                "Expected a God Class finding"
        );

        assertTrue(
                result.findings().stream().allMatch(
                        finding ->
                                Files.exists(
                                        finding.sourceFile()
                                )
                                && finding.startLine() >= 1
                                && finding.endLine()
                                        >= finding.startLine()
                )
        );
    }

    @Test
    void preservesOriginalUnconfiguredBehavior()
            throws IOException {

        createSampleRepository();

        RepositoryAnalyzer analyzer =
                new RepositoryAnalyzer();

        RepositoryAnalysisResult result =
                analyzer.analyze(tempDir);

        assertEquals(2, result.parsedFiles());

        assertEquals(0, result.findingCount());
    }

    @Test
    void producesStableFindingOrderAcrossRepeatedRuns()
            throws IOException {

        createSampleRepository();

        RepositoryAnalyzer analyzer =
                new RepositoryAnalyzer();

        RepositoryAnalysisResult first =
                analyzer.analyze(tempDir, config());

        RepositoryAnalysisResult second =
                analyzer.analyze(tempDir, config());

        List<String> firstIds =
                first.findings().stream()
                        .map(finding -> finding.findingId())
                        .toList();

        List<String> secondIds =
                second.findings().stream()
                        .map(finding -> finding.findingId())
                        .toList();

        assertFalse(firstIds.isEmpty());

        assertEquals(firstIds, secondIds);

        assertEquals(
                firstIds.size(),
                Set.copyOf(firstIds).size(),
                "Finding identifiers must be unique"
        );
    }

    @Test
    void keepsValidFindingsWhenAnotherFileCannotParse()
            throws IOException {

        createSampleRepository();

        write(
                "Broken.java",
                "public class {"
        );

        RepositoryAnalysisResult result =
                new RepositoryAnalyzer().analyze(
                        tempDir,
                        config()
                );

        assertEquals(3, result.totalFiles());
        assertEquals(2, result.parsedFiles());
        assertEquals(1, result.failedFiles());

        assertTrue(result.findingCount() > 0);
    }

    @Test
    void rejectsIncompleteDetectionConfiguration() {

        assertThrows(
                NullPointerException.class,
                () -> new RepositoryDetectionConfig(
                        null,
                        new ClassDetectionThresholds(1, 1, 1),
                        new CohesionDetectionThresholds(0.5, 2),
                        new GodClassDetectionThresholds(4, 2, 0.5)
                )
        );
    }
}
