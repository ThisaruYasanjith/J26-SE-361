
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.NamingDetectionConfig;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.triage.RepositoryTriageResult;
import lk.sliit.codecleanliness.triage.RepositoryTriageService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class PoorNamingIntegrationTest {

    @TempDir
    Path repositoryRoot;

    private RepositoryDetectionConfig config(
            boolean enableNaming) {

        return new RepositoryDetectionConfig(
                new MethodDetectionThresholds(1000, 1000),
                new ClassDetectionThresholds(1000, 1000, 1000),
                new CohesionDetectionThresholds(0.0, 1000),
                new GodClassDetectionThresholds(1000, 1000, 0.0),
                new DuplicateDetectionThresholds(10, 2),
                enableNaming
                        ? new NamingDetectionConfig(true, true, true)
                        : null
        );
    }

    private void createSource() throws Exception {
        Files.writeString(
                repositoryRoot.resolve("bad_type.java"),
                """
                class bad_type {
                    int bad_field;
                    void Bad_method() {}
                }
                """
        );
    }

    @Test
    void includesNamingFindingsInRepositoryTriage()
            throws Exception {

        createSource();

        RepositoryTriageResult result =
                new RepositoryTriageService().analyze(
                        repositoryRoot,
                        config(true)
                );

        var namingFindings = result.analysis()
                .findings()
                .stream()
                .filter(finding ->
                        finding.concern()
                                == MaintainabilityConcern.POOR_NAMING
                )
                .toList();

        assertEquals(3, namingFindings.size());

        assertTrue(namingFindings.stream()
                .anyMatch(finding ->
                        "bad_type".equals(
                                finding.evidence().get("identifier")
                        )));

        assertTrue(result.rankedGroups().stream()
                .flatMap(group ->
                        group.group().findings().stream())
                .anyMatch(finding ->
                        finding.concern()
                                == MaintainabilityConcern.POOR_NAMING
                ));
    }

    @Test
    void namingDetectionIsOptional()
            throws Exception {

        createSource();

        RepositoryTriageResult result =
                new RepositoryTriageService().analyze(
                        repositoryRoot,
                        config(false)
                );

        assertTrue(result.analysis().findings().stream()
                .noneMatch(finding ->
                        finding.concern()
                                == MaintainabilityConcern.POOR_NAMING
                ));
    }
}
