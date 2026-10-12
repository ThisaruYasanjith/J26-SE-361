package lk.sliit.codecleanliness.parsing;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ast.CompilationUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class RepositorySymbolResolverTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldResolveTypeAndMethodAcrossFiles()
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

        RepositorySymbolResolver resolver =
                new RepositorySymbolResolver(tempDir);

        JavaParser parser = new JavaParser(
                resolver.createParserConfiguration()
        );

        CompilationUnit unit = parser.parse(serviceFile)
                .getResult()
                .orElseThrow();

        List<String> types =
                resolver.resolveReferencedTypes(unit);

        List<String> methods =
                resolver.resolveMethodCalls(unit);

        assertTrue(types.contains("example.User"));

        assertTrue(methods.stream().anyMatch(
                method -> method.contains(
                        "example.User.getName()"
                )
        ));
    }
}
