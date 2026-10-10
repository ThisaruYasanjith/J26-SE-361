package lk.sliit.codecleanliness;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class JavaRepositoryParserTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldParseMultipleJavaFiles() throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("User.java"),
                "package example; public class User {}"
        );

        Files.writeString(
                src.resolve("UserService.java"),
                """
                package example;
                public class UserService {
                    public User createUser() {
                        return new User();
                    }
                }
                """
        );

        RepositoryParseResult result =
                new JavaRepositoryParser()
                        .parseRepository(tempDir);

        assertEquals(2, result.totalFiles());
        assertEquals(2, result.successfulFiles());
        assertEquals(0, result.failedFileCount());

        assertTrue(result.parsedFiles().values().stream()
                .anyMatch(unit -> unit.getClassByName("User")
                        .isPresent()));

        assertTrue(result.parsedFiles().values().stream()
                .anyMatch(unit -> unit.getClassByName("UserService")
                        .isPresent()));
    }

    @Test
    void shouldRecordParseFailuresWithoutStopping()
            throws IOException {

        Files.writeString(
                tempDir.resolve("Valid.java"),
                "public class Valid {}"
        );

        Files.writeString(
                tempDir.resolve("Invalid.java"),
                "public class {"
        );

        RepositoryParseResult result =
                new JavaRepositoryParser()
                        .parseRepository(tempDir);

        assertEquals(2, result.totalFiles());
        assertEquals(1, result.successfulFiles());
        assertEquals(1, result.failedFileCount());
    }

    @Test
    void shouldExcludeBuildDirectories() throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java")
        );

        Path target = Files.createDirectories(
                tempDir.resolve("target/generated-sources")
        );

        Files.writeString(
                src.resolve("Application.java"),
                "public class Application {}"
        );

        Files.writeString(
                target.resolve("Generated.java"),
                "public class Generated {}"
        );

        RepositoryParseResult result =
                new JavaRepositoryParser()
                        .parseRepository(tempDir);

        assertEquals(1, result.totalFiles());
        assertEquals(1, result.successfulFiles());
        assertEquals(0, result.failedFileCount());
    }
}