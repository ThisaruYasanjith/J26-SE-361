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

    @Test
        void shouldResolveCrossFileReferencesFromRepositoryParsing()
                throws IOException {

        Path sourceRoot = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                sourceRoot.resolve("User.java"),
                """
                package example;
                public class User {
                        public String getName() {
                        return "Test";
                        }
                }
                """
        );

        Path serviceFile = sourceRoot.resolve("UserService.java");

        Files.writeString(
                serviceFile,
                """
                package example;
                public class UserService {
                        public String displayName() {
                        User user = new User();
                        return user.getName();
                        }
                }
                """
        );

        JavaRepositoryParser repositoryParser =
                new JavaRepositoryParser();

        RepositoryParseResult result =
                repositoryParser.parseRepositoryWithSymbols(tempDir);

        assertEquals(2, result.totalFiles());
        assertEquals(2, result.successfulFiles());
        assertEquals(0, result.failedFileCount());

        var unit = result.parsedFiles().get(serviceFile);

        assertNotNull(unit);

        var userType = unit.findAll(
                com.github.javaparser.ast.type.ClassOrInterfaceType.class
        ).stream()
                .filter(type -> type.getNameAsString().equals("User"))
                .findFirst()
                .orElseThrow();

        assertEquals(
                "example.User",
                userType.resolve()
                        .asReferenceType()
                        .getQualifiedName()
        );

        var methodCall = unit.findAll(
                com.github.javaparser.ast.expr.MethodCallExpr.class
        ).stream()
                .filter(call -> call.getNameAsString().equals("getName"))
                .findFirst()
                .orElseThrow();

        assertTrue(
                methodCall.resolve()
                        .getQualifiedSignature()
                        .contains("example.User.getName()")
        );
    }


}