package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.model.JavaRelationshipInfo;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class RepositoryAnalyzerTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldBuildCombinedRepositoryAnalysis()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Worker.java"),
                """
                package example;

                public interface Worker {
                    void work();
                }
                """
        );

        Files.writeString(
                src.resolve("Employee.java"),
                """
                package example;

                public class Employee implements Worker {
                    public void work() {
                        System.out.println("Working");
                    }
                }
                """
        );

        RepositoryAnalysisResult result =
                new RepositoryAnalyzer().analyze(tempDir);

        assertEquals(2, result.totalFiles());
        assertEquals(2, result.parsedFiles());
        assertEquals(0, result.failedFiles());
        assertEquals(2, result.typeCount());

        assertTrue(result.types().stream().anyMatch(
                type -> type.qualifiedName()
                        .equals("example.Employee")
        ));

        assertTrue(result.relationships().stream().anyMatch(
                relationship ->
                        relationship.kind() ==
                        JavaRelationshipInfo.RelationshipKind.IMPLEMENTS
                        && relationship.target()
                        .equals("example.Worker")
                        && relationship.status() ==
                        JavaRelationshipInfo.ResolutionStatus.RESOLVED
        ));
    }

    @Test
    void shouldPreservePartialAnalysisAndParseFailures()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Valid.java"),
                """
                package example;
                public class Valid {}
                """
        );

        Files.writeString(
                src.resolve("Invalid.java"),
                "public class {"
        );

        RepositoryAnalysisResult result =
                new RepositoryAnalyzer().analyze(tempDir);

        assertEquals(2, result.totalFiles());
        assertEquals(1, result.parsedFiles());
        assertEquals(1, result.failedFiles());
        assertEquals(1, result.typeCount());

        assertTrue(result.parseResult().failedFiles()
                .keySet().stream()
                .anyMatch(path -> path.getFileName()
                        .toString().equals("Invalid.java")));
    }
}
