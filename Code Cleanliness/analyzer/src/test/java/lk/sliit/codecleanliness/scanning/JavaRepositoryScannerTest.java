package lk.sliit.codecleanliness.scanning;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JavaRepositoryScannerTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldFindJavaFilesAcrossPackages() throws IOException {

        Path serviceDir = Files.createDirectories(
                tempDir.resolve("src/main/java/service")
        );

        Path modelDir = Files.createDirectories(
                tempDir.resolve("src/main/java/model")
        );

        Files.writeString(
                serviceDir.resolve("UserService.java"),
                "class UserService {}"
        );

        Files.writeString(
                modelDir.resolve("User.java"),
                "class User {}"
        );

        JavaRepositoryScanner scanner =
                new JavaRepositoryScanner();

        List<Path> files = scanner.scan(tempDir);

        assertEquals(2, files.size());

        assertTrue(files.stream().anyMatch(
                p -> p.getFileName().toString()
                        .equals("UserService.java")
        ));

        assertTrue(files.stream().anyMatch(
                p -> p.getFileName().toString()
                        .equals("User.java")
        ));
    }

    @Test
    void shouldExcludeGeneratedAndBuildFiles() throws IOException {

        Path source = Files.createDirectories(
                tempDir.resolve("src/main/java")
        );

        Path target = Files.createDirectories(
                tempDir.resolve("target/generated-sources")
        );

        Files.writeString(
                source.resolve("Valid.java"),
                "class Valid {}"
        );

        Files.writeString(
                target.resolve("Generated.java"),
                "class Generated {}"
        );

        List<Path> files =
                new JavaRepositoryScanner().scan(tempDir);

        assertEquals(1, files.size());
        assertEquals("Valid.java",
                files.get(0).getFileName().toString());
    }

    @Test
    void shouldRejectInvalidRepository() {

        JavaRepositoryScanner scanner =
                new JavaRepositoryScanner();

        assertThrows(
                IllegalArgumentException.class,
                () -> scanner.scan(tempDir.resolve("missing"))
        );
    }


    @Test
    void shouldSupportCustomDirectoryExclusions() throws IOException {

        Path source = Files.createDirectories(
                tempDir.resolve("src/main/java")
        );

        Path customExcluded = Files.createDirectories(
                tempDir.resolve("custom-output")
        );

        Files.writeString(
                source.resolve("Application.java"),
                "class Application {}"
        );

        Files.writeString(
                customExcluded.resolve("Ignored.java"),
                "class Ignored {}"
        );

        JavaRepositoryScanner scanner =
                new JavaRepositoryScanner(
                        java.util.Set.of("custom-output")
                );

        List<Path> files = scanner.scan(tempDir);

        assertEquals(1, files.size());
        assertEquals(
                "Application.java",
                files.get(0).getFileName().toString()
        );
    }
}
