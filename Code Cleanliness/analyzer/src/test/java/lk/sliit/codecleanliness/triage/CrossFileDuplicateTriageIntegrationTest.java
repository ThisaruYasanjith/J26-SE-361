
package lk.sliit.codecleanliness.triage;

import lk.sliit.codecleanliness.analysis.RepositoryDetectionConfig;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class CrossFileDuplicateTriageIntegrationTest {

    @TempDir
    Path repositoryRoot;

    @Test
    void groupsDuplicatedMethodsAcrossRealJavaFiles()
            throws Exception {

        Files.writeString(
                repositoryRoot.resolve("OrderService.java"),
                """
                class OrderService {
                    int calculateTotal(int amount, int tax) {
                        int subtotal = amount + tax;
                        int adjusted = subtotal * 2;
                        if (adjusted > 100) {
                            adjusted = adjusted - 10;
                        }
                        return adjusted;
                    }
                }
                """
        );

        Files.writeString(
                repositoryRoot.resolve("InvoiceService.java"),
                """
                class InvoiceService {
                    int calculateTotal(int amount, int tax) {
                        int subtotal = amount + tax;
                        int adjusted = subtotal * 2;
                        if (adjusted > 100) {
                            adjusted = adjusted - 10;
                        }
                        return adjusted;
                    }
                }
                """
        );

        RepositoryDetectionConfig config =
                new RepositoryDetectionConfig(
                        new MethodDetectionThresholds(1000, 1000),
                        new ClassDetectionThresholds(
                                1000, 1000, 1000),
                        new CohesionDetectionThresholds(0.0, 1000),
                        new GodClassDetectionThresholds(
                                1000, 1000, 0.0),
                        new DuplicateDetectionThresholds(10, 2)
                );

        RepositoryTriageResult result =
                new RepositoryTriageService()
                        .analyze(repositoryRoot, config);

        var duplicateFindings =
                result.analysis().findings().stream()
                        .filter(finding ->
                                finding.concern()
                                        == MaintainabilityConcern
                                                .DUPLICATED_LOGIC)
                        .toList();

        assertEquals(
                2,
                duplicateFindings.size(),
                "Both duplicated method occurrences should be detected"
        );

        var crossFileGroups = result.groups().stream()
                .filter(group ->
                        "CROSS_FILE_DUPLICATED_LOGIC".equals(
                                group.relationshipType()))
                .toList();

        assertEquals(
                1,
                crossFileGroups.size(),
                "The two occurrences should form one cross-file group"
        );

        IssueGroup group = crossFileGroups.get(0);

        assertEquals(2, group.findingCount());

        Set<String> files = group.findings().stream()
                .map(finding ->
                        finding.sourceFile()
                                .getFileName()
                                .toString())
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("OrderService.java", "InvoiceService.java"),
                files
        );

        assertTrue(
                result.rankedGroups().stream()
                        .anyMatch(ranked ->
                                ranked.group().groupId()
                                        .equals(group.groupId())),
                "The cross-file group must reach priority ranking"
        );
    }
}
