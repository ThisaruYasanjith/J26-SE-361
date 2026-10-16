
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.analysis.RepositoryDetectionConfig;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class RepositoryTriageServiceTest {

    @TempDir
    Path tempDir;

    private final RepositoryTriageService service =
            new RepositoryTriageService();

    private RepositoryDetectionConfig config() {
        // Synthetic test boundaries, not calibrated thresholds.
        return new RepositoryDetectionConfig(
                new MethodDetectionThresholds(1, 1),
                new ClassDetectionThresholds(1, 1, 1),
                new CohesionDetectionThresholds(0.5, 2),
                new GodClassDetectionThresholds(4, 2, 0.5)
        );
    }

    private void createRepository() throws IOException {
        Path source = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                source.resolve("Sample.java"),
                """
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

                    void customerTask(boolean active) {
                        if (active) {
                            customer.balance++;
                        }
                    }

                    void orderTask(boolean valid) {
                        if (valid) {
                            order.quantity++;
                        }
                    }
                }
                """
        );

        Files.writeString(
                source.resolve("Other.java"),
                """
                package example;

                public class Other {
                    void process(boolean first, boolean second) {
                        if (first) {
                            System.out.println("A");
                        }
                        if (second) {
                            System.out.println("B");
                        }
                    }
                }
                """
        );
    }

    @Test
    void connectsDetectionGroupingAndRanking()
            throws IOException {

        createRepository();

        RepositoryTriageResult result =
                service.analyze(tempDir, config());

        assertEquals(2, result.analysis().parsedFiles());
        assertEquals(0, result.analysis().failedFiles());

        assertTrue(result.findingCount() > 0);
        assertTrue(result.groupCount() > 0);

        assertEquals(
                result.groupCount(),
                result.rankedGroups().size()
        );

        int groupedFindings = result.groups()
                .stream()
                .mapToInt(IssueGroup::findingCount)
                .sum();

        assertEquals(
                result.findingCount(),
                groupedFindings
        );

        Set<MaintainabilityConcern> concerns =
                result.analysis().findings().stream()
                        .map(finding -> finding.concern())
                        .collect(Collectors.toSet());

        assertTrue(
                concerns.contains(MaintainabilityConcern.LONG_METHOD)
        );
        assertTrue(
                concerns.contains(MaintainabilityConcern.HIGH_COMPLEXITY)
        );
        assertTrue(
                concerns.contains(MaintainabilityConcern.LARGE_CLASS)
        );
        assertTrue(
                concerns.contains(MaintainabilityConcern.WEAK_COHESION)
        );
        assertTrue(
                concerns.contains(MaintainabilityConcern.GOD_CLASS)
        );

        assertTrue(
                result.groups().stream()
                        .anyMatch(IssueGroup::containsRelatedFindings)
        );

        for (int i = 0; i < result.rankedGroups().size(); i++) {
            RankedIssueGroup ranked =
                    result.rankedGroups().get(i);

            assertEquals(i + 1, ranked.rank());
            assertFalse(ranked.explanation().isBlank());
        }
    }

    @Test
    void producesStableEndToEndRanking()
            throws IOException {

        createRepository();

        RepositoryTriageResult first =
                service.analyze(tempDir, config());

        RepositoryTriageResult second =
                service.analyze(tempDir, config());

        assertEquals(
                first.rankedGroups(),
                second.rankedGroups()
        );
    }

    @Test
    void handlesRepositoryWithoutDetectedFindings()
            throws IOException {

        Path source = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                source.resolve("Empty.java"),
                """
                package example;
                public class Empty {}
                """
        );

        RepositoryTriageResult result =
                service.analyze(
                        tempDir,
                        new RepositoryDetectionConfig(
                                new MethodDetectionThresholds(1000, 1000),
                                new ClassDetectionThresholds(1000, 1000, 1000),
                                new CohesionDetectionThresholds(0.0, 1000),
                                new GodClassDetectionThresholds(
                                        1000, 1000, 0.0
                                )
                        )
                );

        assertEquals(0, result.findingCount());
        assertEquals(0, result.groupCount());
        assertTrue(result.rankedGroups().isEmpty());
    }

    @Test
    void retainsPartialResultsWhenSourceFileFailsToParse()
            throws IOException {

        createRepository();

        Path source = tempDir.resolve(
                "src/main/java/example"
        );

        Files.writeString(
                source.resolve("Broken.java"),
                "public class {"
        );

        RepositoryTriageResult result =
                service.analyze(tempDir, config());

        assertEquals(3, result.analysis().totalFiles());
        assertEquals(2, result.analysis().parsedFiles());
        assertEquals(1, result.analysis().failedFiles());

        assertTrue(result.findingCount() > 0);
        assertEquals(
                result.groupCount(),
                result.rankedGroups().size()
        );
    }
}
