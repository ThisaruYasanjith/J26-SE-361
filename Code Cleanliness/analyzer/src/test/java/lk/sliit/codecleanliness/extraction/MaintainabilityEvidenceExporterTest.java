package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.analysis.RepositoryDetectionConfig;
import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.triage.RepositoryTriageResult;
import lk.sliit.codecleanliness.triage.RepositoryTriageService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class MaintainabilityEvidenceExporterTest {

    @TempDir
    Path tempDir;

    private RepositoryDetectionConfig config() {
        // Test-only deterministic profile, NOT a calibrated detector configuration.
        return new RepositoryDetectionConfig(
                new MethodDetectionThresholds(30, 10),
                new ClassDetectionThresholds(300, 25, 15),
                new CohesionDetectionThresholds(0.33, 2),
                new GodClassDetectionThresholds(47, 5, 0.33)
        );
    }

    @Test
    void longMethodKeepsBothEndsOfBoundedContext() throws Exception {
        Path repository = Files.createDirectory(tempDir.resolve("long-repo"));
        StringBuilder source = new StringBuilder("public class LongSample {\n  public int calculate() {\n    int total = 0;\n");
        for (int index = 0; index < 120; index++) {
            source.append("    total += ").append(index).append(";\n");
        }
        source.append("    return total;\n  }\n}\n");
        Files.writeString(repository.resolve("LongSample.java"), source.toString(), StandardCharsets.UTF_8);

        RepositoryTriageResult triage = new RepositoryTriageService().analyze(repository, config());
        assertTrue(triage.findingCount() > 0, "Expected a long-method finding");
        Path output = tempDir.resolve("long-report.json");
        new MaintainabilityEvidenceExporter().export(repository, triage, output);
        String json = Files.readString(output);

        assertTrue(json.contains("AVAILABLE_TRUNCATED_SOURCE_CONTEXT"));
        assertTrue(json.contains("\"truncated\":true"));
        assertTrue(json.contains("middle source lines omitted"));
        assertTrue(json.contains("total += 0;"));
        assertTrue(json.contains("return total;"));
        assertTrue(json.contains("\"schema_version\":\"1.1\""));
    }

    @Test
    void shortMethodRetainsUntruncatedLineNumberedContext() throws Exception {
        Path repository = Files.createDirectory(tempDir.resolve("short-repo"));
        String source = "public class ShortSample {\n"
                + "  int calculate(int a) {\n"
                + "    if (a > 1) return a;\n"
                + "    return 0;\n"
                + "  }\n"
                + "}\n";
        Files.writeString(repository.resolve("ShortSample.java"), source, StandardCharsets.UTF_8);
        RepositoryDetectionConfig sensitive = new RepositoryDetectionConfig(
                new MethodDetectionThresholds(1, 1),
                new ClassDetectionThresholds(300, 25, 15),
                new CohesionDetectionThresholds(0.33, 2),
                new GodClassDetectionThresholds(47, 5, 0.33)
        );
        RepositoryTriageResult triage = new RepositoryTriageService().analyze(repository, sensitive);
        assertTrue(triage.findingCount() > 0);
        Path output = tempDir.resolve("short-report.json");
        new MaintainabilityEvidenceExporter().export(repository, triage, output);
        String json = Files.readString(output);
        assertTrue(json.contains("AVAILABLE_PARTIAL_FILE_CONTEXT"));
        assertTrue(json.contains("\"truncated\":false"));
        assertTrue(json.contains("return a;"));
    }
}
