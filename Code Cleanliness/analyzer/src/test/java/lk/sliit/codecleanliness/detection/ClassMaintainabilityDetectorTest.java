
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ClassMaintainabilityDetectorTest {

    private final ClassMaintainabilityDetector detector =
            new ClassMaintainabilityDetector();

    private RepositoryParseResult repository(String... sources) {

        Path root = Path.of("synthetic-repository");

        Map<Path, CompilationUnit> parsed = new LinkedHashMap<>();

        for (int i = 0; i < sources.length; i++) {

            Path file = root.resolve("File" + (i + 1) + ".java");

            parsed.put(file, StaticJavaParser.parse(sources[i]));
        }

        return new RepositoryParseResult(
                root,
                List.copyOf(parsed.keySet()),
                parsed,
                Map.of()
        );
    }

    @Test
    void detectsLargeClassWhenMethodCountExceedsBoundary() {

        RepositoryParseResult repository = repository("""
                class Example {
                    void first() {}
                    void second() {}
                    void third() {}
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new ClassDetectionThresholds(100, 2, 10)
                );

        assertEquals(1, findings.size());

        MaintainabilityFinding finding = findings.get(0);

        assertEquals(
                MaintainabilityConcern.LARGE_CLASS,
                finding.concern()
        );

        assertEquals(FindingScope.CLASS, finding.scope());

        assertEquals(
                "3",
                finding.evidence().get("methodCount")
        );

        assertEquals(
                "true",
                finding.evidence().get("exceedsMethods")
        );
    }

    @Test
    void doesNotReportClassWithinAllBoundaries() {

        RepositoryParseResult repository = repository("""
                class Small {
                    private int value;
                    void work() {
                        value++;
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new ClassDetectionThresholds(20, 5, 5)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void distinguishesNestedClassesAndMultipleFiles() {

        RepositoryParseResult repository = repository(
                """
                package example;
                class Outer {
                    class Inner {
                        void first() {}
                        void second() {}
                        void third() {}
                    }
                }
                """,
                """
                package example;
                class Other {
                    void first() {}
                    void second() {}
                    void third() {}
                }
                """
        );

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new ClassDetectionThresholds(100, 2, 10)
                );

        assertEquals(2, findings.size());

        assertEquals(
                2,
                findings.stream()
                        .map(MaintainabilityFinding::findingId)
                        .distinct()
                        .count()
        );

        assertTrue(findings.stream().anyMatch(
                finding -> finding.symbolName().contains("Inner")
        ));
    }

    @Test
    void excludesInterfacesFromPreliminaryClassRule() {

        RepositoryParseResult repository = repository("""
                interface Worker {
                    void first();
                    void second();
                    void third();
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new ClassDetectionThresholds(1, 1, 1)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void rejectsInvalidClassBoundaries() {

        assertThrows(
                IllegalArgumentException.class,
                () -> new ClassDetectionThresholds(0, 5, 5)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new ClassDetectionThresholds(5, 0, 5)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new ClassDetectionThresholds(5, 5, 0)
        );
    }
}
