package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DuplicateCandidateFinderTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldFindNormalizedDuplicatesAcrossFiles()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(src.resolve("First.java"), """
                package example;
                public class First {
                    public int calculate(int a, int b) {
                        int total = a + b;
                        return total;
                    }
                }
                """);

        Files.writeString(src.resolve("Second.java"), """
                package example;
                public class Second {
                    public int compute(int x, int y) {
                        int result = x + y;
                        return result;
                    }
                }
                """);

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        var groups =
                new DuplicateCandidateFinder().findCandidates(parsed);

        assertEquals(1, groups.size());
        assertEquals(2, groups.get(0).size());

        assertNotEquals(
                groups.get(0).get(0).sourceFile(),
                groups.get(0).get(1).sourceFile()
        );
    }

    @Test
    void shouldNotGroupDifferentOperations()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(src.resolve("MathOps.java"), """
                package example;
                public class MathOps {
                    public int add(int a, int b) {
                        return a + b;
                    }

                    public int subtract(int a, int b) {
                        return a - b;
                    }
                }
                """);

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        var groups =
                new DuplicateCandidateFinder().findCandidates(parsed);

        assertTrue(groups.isEmpty());
    }
}