
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class GodClassDetectorTest {

    @TempDir
    Path tempDir;

    private final GodClassDetector detector =
            new GodClassDetector();

    private RepositoryParseResult parse(String source)
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Sample.java"),
                source
        );

        return new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);
    }

    @Test
    void detectsCompositeGodClassCandidate()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                class Customer {
                    int balance;
                }

                class Order {
                    int quantity;
                }

                public class Sample {

                    Customer customer = new Customer();
                    Order order = new Order();

                    void processCustomer(boolean active) {
                        if (active) {
                            customer.balance++;
                        }
                    }

                    void processOrder(boolean valid) {
                        if (valid) {
                            order.quantity++;
                        }
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new GodClassDetectionThresholds(4, 2, 0.5)
                );

        assertEquals(1, findings.size());

        MaintainabilityFinding finding = findings.get(0);

        assertEquals(
                MaintainabilityConcern.GOD_CLASS,
                finding.concern()
        );

        assertEquals("2", finding.evidence().get("atfd"));
        assertEquals("0.0", finding.evidence().get("tcc"));
    }

    @Test
    void doesNotFlagWhenAtfdIsBelowBoundary()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                class Customer {
                    int balance;
                }

                public class Sample {

                    Customer customer = new Customer();

                    void first(boolean active) {
                        if (active) {
                            customer.balance++;
                        }
                    }

                    void second(boolean active) {
                        if (active) {
                            customer.balance--;
                        }
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new GodClassDetectionThresholds(4, 2, 0.5)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void skipsIncompleteResolutionEvidence()
            throws IOException {

        RepositoryParseResult repository = parse("""
                package example;

                class Customer {
                    int balance;
                }

                class Order {
                    int quantity;
                }

                public class Sample {

                    Customer customer = new Customer();
                    Order order = new Order();

                    void first(boolean active) {
                        if (active) {
                            customer.balance++;
                            unknownCall();
                        }
                    }

                    void second(boolean valid) {
                        if (valid) {
                            order.quantity++;
                        }
                    }
                }
                """);

        List<MaintainabilityFinding> findings =
                detector.detect(
                        repository,
                        new GodClassDetectionThresholds(4, 2, 0.5)
                );

        assertTrue(findings.isEmpty());
    }

    @Test
    void rejectsInvalidThresholds() {

        assertThrows(
                IllegalArgumentException.class,
                () -> new GodClassDetectionThresholds(0, 2, 0.5)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new GodClassDetectionThresholds(4, 0, 0.5)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new GodClassDetectionThresholds(4, 2, -0.1)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new GodClassDetectionThresholds(
                        4, 2, Double.NaN
                )
        );
    }
}
