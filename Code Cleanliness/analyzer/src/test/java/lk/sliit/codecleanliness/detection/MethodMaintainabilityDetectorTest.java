
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MethodMaintainabilityDetectorTest {

    private final MethodMaintainabilityDetector detector =
            new MethodMaintainabilityDetector();

    private RepositoryParseResult repository(String... sources) {

        Path root = Path.of("synthetic-repository");
        java.util.LinkedHashMap<Path, CompilationUnit> parsed =
                new java.util.LinkedHashMap<>();

        int index = 1;

        for (String source : sources) {
            Path file = root.resolve("File" + index++ + ".java");
            parsed.put(file, StaticJavaParser.parse(source));
        }

        return new RepositoryParseResult(
                root,
                List.copyOf(parsed.keySet()),
                parsed,
                Map.of()
        );
    }

    @Test
    void detectsLongMethodUsingConfiguredBoundary() {

        RepositoryParseResult repository = repository("""
                class Example {
                    void process() {
                        int a = 1;
                        int b = 2;
                        int c = 3;
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new MethodDetectionThresholds(2, 10)
                );

        assertEquals(1, findings.size());
        assertEquals(
                MaintainabilityConcern.LONG_METHOD,
                findings.get(0).concern()
        );

        assertEquals(
                "3",
                findings.get(0).evidence().get("ncss")
        );
    }

    @Test
    void detectsHighComplexityUsingConfiguredBoundary() {

        RepositoryParseResult repository = repository("""
                class Example {
                    void process(boolean a, boolean b) {
                        if (a) {
                            System.out.println("A");
                        }
                        if (b) {
                            System.out.println("B");
                        }
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new MethodDetectionThresholds(20, 2)
                );

        assertEquals(1, findings.size());
        assertEquals(
                MaintainabilityConcern.HIGH_COMPLEXITY,
                findings.get(0).concern()
        );

        assertEquals(
                "3",
                findings.get(0).evidence()
                        .get("cyclomaticComplexity")
        );
    }

    @Test
    void doesNotReportMethodsWithinBoundaries() {

        RepositoryParseResult repository = repository("""
                class Example {
                    void simple() {
                        System.out.println("Hello");
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new MethodDetectionThresholds(10, 10)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void distinguishesOverloadedMethodsAcrossFiles() {

        RepositoryParseResult repository = repository(
                """
                class First {
                    void process(int value) {
                        int a = 1;
                        int b = 2;
                        int c = 3;
                    }

                    void process(String value) {
                        int a = 1;
                        int b = 2;
                        int c = 3;
                    }
                }
                """,
                """
                class Second {
                    void process() {
                        int a = 1;
                        int b = 2;
                        int c = 3;
                    }
                }
                """
        );

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new MethodDetectionThresholds(2, 10)
                );

        assertEquals(3, findings.size());

        assertEquals(
                3,
                findings.stream()
                        .map(MaintainabilityFinding::findingId)
                        .distinct()
                        .count()
        );
    }

    @Test
    void rejectsInvalidDetectionBoundaries() {

        assertThrows(
                IllegalArgumentException.class,
                () -> new MethodDetectionThresholds(0, 5)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new MethodDetectionThresholds(5, 0)
        );
    }

    @Test
    void identifiesNestedMethodOwner() {

        RepositoryParseResult repository = repository("""
                class Outer {
                        class Helper {
                        void process() {
                                int a = 1;
                                int b = 2;
                                int c = 3;
                        }
                        }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new MethodDetectionThresholds(2, 10)
                );

        assertEquals(1, findings.size());

        assertTrue(
                findings.get(0).symbolName()
                        .contains("Outer.Helper.process()")
        );
    }

}
