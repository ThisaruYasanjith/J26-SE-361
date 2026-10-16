
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class WeakCohesionDetectorTest {

    @TempDir
    Path tempDir;

    private final WeakCohesionDetector detector =
            new WeakCohesionDetector();

    private RepositoryParseResult parse(String source)
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Sample.java"),
                source
        );

        return new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);
    }

    @Test
    void detectsDisconnectedMethodGroups()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                public class Sample {
                    private int count;
                    private String name;

                    public void increment() {
                        count++;
                    }

                    public void rename() {
                        name = "Updated";
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new CohesionDetectionThresholds(0.5, 2)
                );

        assertEquals(1, findings.size());

        MaintainabilityFinding finding = findings.get(0);

        assertEquals(
                MaintainabilityConcern.WEAK_COHESION,
                finding.concern()
        );

        assertEquals("0.0", finding.evidence().get("tcc"));
        assertEquals("2", finding.evidence().get("lcom4"));
    }

    @Test
    void doesNotFlagMethodsSharingAField()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                public class Sample {
                    private int count;

                    public void increment() {
                        count++;
                    }

                    public int read() {
                        return count;
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new CohesionDetectionThresholds(0.5, 2)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void doesNotFlagSingleMethodClass()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                public class Sample {
                    public void work() {
                        System.out.println("Hello");
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new CohesionDetectionThresholds(0.5, 2)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void skipsClassWithUnresolvedMethodReference()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                public class Sample {
                    private int count;
                    private String name;

                    public void first() {
                        count++;
                        missingDependency();
                    }

                    public void second() {
                        name = "Updated";
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new CohesionDetectionThresholds(0.5, 2)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void rejectsInvalidThresholds() {

        assertThrows(
                IllegalArgumentException.class,
                () -> new CohesionDetectionThresholds(-0.1, 2)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new CohesionDetectionThresholds(1.1, 2)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new CohesionDetectionThresholds(0.5, 1)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new CohesionDetectionThresholds(
                        Double.NaN, 2
                )
        );
    }
}
