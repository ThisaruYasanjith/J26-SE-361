
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class IspRiskDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect(String code) throws Exception {

        Files.writeString(root.resolve("Example.java"), code);

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new IspRiskDetector().detect(repository);
    }

    @Test
    void detectsUnsupportedInterfaceOperation()
            throws Exception {

        var findings = detect(
                """
                interface Worker {
                    void work();
                    void eat();
                }

                class Robot implements Worker {
                    public void work() {}

                    public void eat() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.ISP_RISK,
                findings.get(0).concern()
        );
    }

    @Test
    void acceptsSupportedInterfaceImplementation()
            throws Exception {

        var findings = detect(
                """
                interface Worker {
                    void work();
                }

                class Robot implements Worker {
                    public void work() {
                        System.out.println("Working");
                    }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void ignoresClassWithoutInterfaces()
            throws Exception {

        var findings = detect(
                """
                class Example {
                    void execute() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertTrue(findings.isEmpty());
    }

    @Test
    void isDeterministic()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                interface Task {
                    void execute();
                }

                class TaskImpl implements Task {
                    public void execute() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new IspRiskDetector();

        assertEquals(
                detector.detect(repository),
                detector.detect(repository)
        );
    }

    @Test
        void ignoresUnsupportedMethodOutsideInterfaceContract()
            throws Exception {

        var findings = detect(
                """
                interface Worker {
                    void work();
                }

                class Robot implements Worker {

                    public void work() {}

                    void unrelatedOperation() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        assertTrue(
                findings.isEmpty(),
                "Only methods belonging to the implemented "
                        + "interface contract should be considered"
        );
    }

    @Test
        void detectsUnsupportedInterfaceMethodAcrossFiles()
            throws Exception {

        Files.writeString(
                root.resolve("Worker.java"),
                """
                interface Worker {
                    void work();
                    void eat();
                }
                """
        );

        Files.writeString(
                root.resolve("Robot.java"),
                """
                class Robot implements Worker {

                    public void work() {}

                    public void eat() {
                        throw new UnsupportedOperationException();
                    }
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var findings = new IspRiskDetector()
                .detect(repository);

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.ISP_RISK,
                findings.get(0).concern()
        );

        assertTrue(
                findings.get(0)
                        .evidence()
                        .get("matchedInterfaces")
                        .contains("Worker")
        );
    }

}
