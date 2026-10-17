
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LspRiskDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect(String code) throws Exception {

        Files.writeString(root.resolve("Example.java"), code);

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new LspRiskDetector().detect(repository);
    }

    @Test
    void detectsUnsupportedOverriddenMethod()
            throws Exception {

        var findings = detect(
                """
                class Bird {
                    void fly() {}
                }

                class Penguin extends Bird {
                    @Override
                    void fly() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.LSP_RISK,
                findings.get(0).concern()
        );

        assertEquals(
                "OVERRIDE_UNSUPPORTED_OPERATION",
                findings.get(0).ruleId()
        );
    }

    @Test
    void acceptsSupportedOverride()
            throws Exception {

        var findings = detect(
                """
                class Parent {
                    int calculate() {
                        return 1;
                    }
                }

                class Child extends Parent {
                    @Override
                    int calculate() {
                        return 2;
                    }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void ignoresUnrelatedUnsupportedOperation()
            throws Exception {

        var findings = detect(
                """
                class Standalone {
                    void process() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void requiresOverrideEvidence()
            throws Exception {

        var findings = detect(
                """
                class Parent {
                    void process() {}
                }

                class Child extends Parent {
                    void otherOperation() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void producesDeterministicResults()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                class Parent {
                    void execute() {}
                }

                class Child extends Parent {
                    @Override
                    void execute() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new LspRiskDetector();

        assertEquals(
                detector.detect(repository),
                detector.detect(repository)
        );
    }
}
