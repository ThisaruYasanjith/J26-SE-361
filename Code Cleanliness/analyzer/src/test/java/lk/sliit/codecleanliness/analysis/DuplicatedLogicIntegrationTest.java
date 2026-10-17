
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.triage.RepositoryTriageResult;
import lk.sliit.codecleanliness.triage.RepositoryTriageService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DuplicatedLogicIntegrationTest {

    @TempDir
    Path repositoryRoot;

    private RepositoryDetectionConfig config(boolean includeDuplicates) {
        MethodDetectionThresholds methods =
                new MethodDetectionThresholds(1000, 1000);

        ClassDetectionThresholds classes =
                new ClassDetectionThresholds(1000, 1000, 1000);

        CohesionDetectionThresholds cohesion =
                new CohesionDetectionThresholds(0.0, 1000);

        GodClassDetectionThresholds godClass =
                new GodClassDetectionThresholds(1000, 1000, 0.0);

        if (!includeDuplicates) {
            return new RepositoryDetectionConfig(
                    methods, classes, cohesion, godClass
            );
        }

        return new RepositoryDetectionConfig(
                methods, classes, cohesion, godClass,
                new DuplicateDetectionThresholds(10, 2)
        );
    }

    private void createSources() throws Exception {
        Path folder = Files.createDirectories(
                repositoryRoot.resolve("src/main/java/example")
        );

        String first = """
                package example;
                public class First {
                    public int compute(int a, int b) {
                        int sum = a + b;
                        if (sum > 10) {
                            sum = sum * 2;
                        }
                        return sum;
                    }
                }
                """;

        String second = first.replace(
                "class First", "class Second"
        );

        Files.writeString(folder.resolve("First.java"), first);
        Files.writeString(folder.resolve("Second.java"), second);
    }

    @Test
    void repositoryTriageIncludesCrossFileDuplication()
            throws Exception {

        createSources();

        RepositoryTriageResult result =
                new RepositoryTriageService().analyze(
                        repositoryRoot,
                        config(true)
                );

        var duplicateFindings =
                result.analysis().findings().stream()
                        .filter(finding ->
                                finding.concern()
                                        == MaintainabilityConcern.DUPLICATED_LOGIC)
                        .toList();

        assertEquals(2, duplicateFindings.size());

        assertEquals(
                2,
                duplicateFindings.stream()
                        .map(finding -> finding.sourceFile())
                        .distinct()
                        .count()
        );

        assertTrue(result.rankedGroups().stream()
                .flatMap(group -> group.group().findings().stream())
                .anyMatch(finding ->
                        finding.concern()
                                == MaintainabilityConcern.DUPLICATED_LOGIC
                ));
    }

    @Test
    void oldConfigurationDoesNotEnableDuplication()
            throws Exception {

        createSources();

        RepositoryTriageResult result =
                new RepositoryTriageService().analyze(
                        repositoryRoot,
                        config(false)
                );

        assertTrue(result.analysis().findings().stream()
                .noneMatch(finding ->
                        finding.concern()
                                == MaintainabilityConcern.DUPLICATED_LOGIC
                ));
    }
}
