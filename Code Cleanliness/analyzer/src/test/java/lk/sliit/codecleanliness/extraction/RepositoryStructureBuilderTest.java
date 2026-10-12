package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.model.JavaTypeInfo;
import lk.sliit.codecleanliness.model.RepositoryParseResult;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class RepositoryStructureBuilderTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldExtractClassesInterfacesMethodsAndFields()
            throws IOException {

        Path sourceRoot = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                sourceRoot.resolve("Named.java"),
                """
                package example;

                public interface Named {
                    String getName();
                }
                """
        );

        Files.writeString(
                sourceRoot.resolve("User.java"),
                """
                package example;

                public class User implements Named {
                    private String name;

                    public String getName() {
                        return name;
                    }
                }
                """
        );

        RepositoryParseResult parsed =
                new JavaRepositoryParser()
                        .parseRepositoryWithSymbols(tempDir);

        assertEquals(2, parsed.successfulFiles());
        assertEquals(0, parsed.failedFileCount());

        List<JavaTypeInfo> types =
                new RepositoryStructureBuilder().build(parsed);

        assertEquals(2, types.size());

        JavaTypeInfo user = types.stream()
                .filter(type ->
                        type.qualifiedName().equals("example.User"))
                .findFirst()
                .orElseThrow();

        assertEquals("CLASS", user.kind());
        assertTrue(user.line() > 0);

        assertEquals(1, user.fields().size());
        assertEquals("name", user.fields().get(0).name());

        assertEquals(1, user.methods().size());
        assertEquals("getName", user.methods().get(0).name());
        assertEquals("String", user.methods().get(0).returnType());

        assertTrue(user.implementedTypes().contains("Named"));

        JavaTypeInfo named = types.stream()
                .filter(type ->
                        type.qualifiedName().equals("example.Named"))
                .findFirst()
                .orElseThrow();

        assertEquals("INTERFACE", named.kind());
        assertEquals(1, named.methods().size());
    }
}
