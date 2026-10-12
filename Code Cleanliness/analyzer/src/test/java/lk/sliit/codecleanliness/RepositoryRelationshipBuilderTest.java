package lk.sliit.codecleanliness;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class RepositoryRelationshipBuilderTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldResolveCrossFileImplementationAndMethodCall()
            throws IOException {

        Path sourceRoot = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                sourceRoot.resolve("PaymentProcessor.java"),
                """
                package example;
                public interface PaymentProcessor {
                    boolean process();
                }
                """
        );

        Files.writeString(
                sourceRoot.resolve("PaymentValidator.java"),
                """
                package example;
                public class PaymentValidator {
                    public boolean validate() {
                        return true;
                    }
                }
                """
        );

        Files.writeString(
                sourceRoot.resolve("PaymentService.java"),
                """
                package example;
                public class PaymentService
                        implements PaymentProcessor {

                    public boolean process() {
                        PaymentValidator validator =
                                new PaymentValidator();
                        return validator.validate();
                    }
                }
                """
        );

        RepositoryParseResult parsed =
                new JavaRepositoryParser()
                        .parseRepositoryWithSymbols(tempDir);

        assertEquals(3, parsed.successfulFiles());
        assertEquals(0, parsed.failedFileCount());

        List<JavaRelationshipInfo> relationships =
                new RepositoryRelationshipBuilder().build(parsed);

        assertTrue(relationships.stream().anyMatch(
                r -> r.sourceType().equals("example.PaymentService")
                        && r.kind() ==
                        JavaRelationshipInfo.RelationshipKind.IMPLEMENTS
                        && r.target().equals("example.PaymentProcessor")
                        && r.status() ==
                        JavaRelationshipInfo.ResolutionStatus.RESOLVED
        ));

        assertTrue(relationships.stream().anyMatch(
        r -> r.sourceType().equals("example.PaymentService")
                && r.kind() ==
                JavaRelationshipInfo.RelationshipKind.METHOD_CALL
                && "process".equals(r.sourceMethod())
                && r.target().contains(
                        "example.PaymentValidator.validate()"
                )
                && r.status() ==
                JavaRelationshipInfo.ResolutionStatus.RESOLVED
        ));
    }

    @Test
    void shouldRecordUnresolvedMethodCall()
            throws IOException {

        Path sourceRoot = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                sourceRoot.resolve("BrokenService.java"),
                """
                package example;
                public class BrokenService {
                    public void execute() {
                        MissingHelper.perform();
                    }
                }
                """
        );

        RepositoryParseResult parsed =
                new JavaRepositoryParser()
                        .parseRepositoryWithSymbols(tempDir);

        assertEquals(1, parsed.successfulFiles());

        List<JavaRelationshipInfo> relationships =
                new RepositoryRelationshipBuilder().build(parsed);

        assertTrue(relationships.stream().anyMatch(
                r -> r.kind() ==
                        JavaRelationshipInfo.RelationshipKind.METHOD_CALL
                        && r.target().contains("perform")
                        && r.status() ==
                        JavaRelationshipInfo.ResolutionStatus.UNRESOLVED
        ));
    }
}