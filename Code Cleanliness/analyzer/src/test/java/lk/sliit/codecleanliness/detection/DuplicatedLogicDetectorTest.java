
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

class DuplicatedLogicDetectorTest {

    @TempDir
    Path repositoryRoot;

    private final DuplicatedLogicDetector detector =
            new DuplicatedLogicDetector();

    private RepositoryParseResult parse() throws IOException {
        return new JavaRepositoryParser()
                .parseRepositoryWithSymbols(repositoryRoot);
    }

    private void write(
            String fileName,
            String code
    ) throws IOException {

        Path path = repositoryRoot.resolve(fileName);

        Files.createDirectories(path.getParent());
        Files.writeString(path, code);
    }

    private DuplicateDetectionThresholds thresholds() {
        return new DuplicateDetectionThresholds(10, 2);
    }

    @Test
    void detectsIdenticalBodiesAcrossDifferentFiles()
            throws IOException {

        write(
                "src/example/First.java",
                """
                package example;
                public class First {
                    public int total(int a, int b) {
                        int sum = a + b;
                        if (sum > 10) {
                            sum = sum * 2;
                        }
                        return sum;
                    }
                }
                """
        );

        write(
                "src/example/Second.java",
                """
                package example;
                public class Second {
                    public int total(int a, int b) {
                        int sum = a + b;
                        if (sum > 10) {
                            sum = sum * 2;
                        }
                        return sum;
                    }
                }
                """
        );

        List<MaintainabilityFinding> findings =
                detector.detect(parse(), thresholds());

        assertEquals(2, findings.size());

        assertTrue(findings.stream().allMatch(
                finding -> finding.concern()
                        == MaintainabilityConcern.DUPLICATED_LOGIC
        ));

        assertEquals(
                2,
                findings.stream()
                        .map(MaintainabilityFinding::sourceFile)
                        .distinct()
                        .count()
        );

        assertTrue(findings.stream().allMatch(
                finding -> "2".equals(
                        finding.evidence().get("occurrenceCount")
                )
        ));
    }

    @Test
    void doesNotReportDifferentMethodBodies()
            throws IOException {

        write(
                "src/example/First.java",
                """
                package example;
                public class First {
                    int first(int x) {
                        int y = x + 1;
                        if (y > 5) {
                            y = y * 2;
                        }
                        return y;
                    }
                }
                """
        );

        write(
                "src/example/Second.java",
                """
                package example;
                public class Second {
                    int second(int x) {
                        int y = x - 1;
                        if (y < 5) {
                            y = y / 2;
                        }
                        return y;
                    }
                }
                """
        );

        assertTrue(
                detector.detect(parse(), thresholds()).isEmpty()
        );
    }

    @Test
    void respectsMinimumOccurrenceBoundary()
            throws IOException {

        write(
                "src/example/First.java",
                """
                package example;
                public class First {
                    int calculate(int value) {
                        int result = value + 1;
                        if (result > 10) {
                            result = result * 2;
                        }
                        return result;
                    }
                }
                """
        );

        write(
                "src/example/Second.java",
                """
                package example;
                public class Second {
                    int calculate(int value) {
                        int result = value + 1;
                        if (result > 10) {
                            result = result * 2;
                        }
                        return result;
                    }
                }
                """
        );

        assertTrue(
                detector.detect(
                        parse(),
                        new DuplicateDetectionThresholds(10, 3)
                ).isEmpty()
        );
    }

    @Test
    void handlesRepositoryWithoutDuplicateCandidates()
            throws IOException {

        write(
                "src/example/Empty.java",
                """
                package example;
                public class Empty {}
                """
        );

        assertTrue(
                detector.detect(parse(), thresholds()).isEmpty()
        );
    }

    @Test
    void producesDeterministicFindings()
            throws IOException {

        write(
                "src/example/First.java",
                """
                package example;
                public class First {
                    int compute(int x) {
                        int result = x + 1;
                        if (result > 5) {
                            result = result * 3;
                        }
                        return result;
                    }
                }
                """
        );

        write(
                "src/example/Second.java",
                """
                package example;
                public class Second {
                    int compute(int x) {
                        int result = x + 1;
                        if (result > 5) {
                            result = result * 3;
                        }
                        return result;
                    }
                }
                """
        );

        RepositoryParseResult repository = parse();

        assertEquals(
                detector.detect(repository, thresholds()),
                detector.detect(repository, thresholds())
        );
    }
}
