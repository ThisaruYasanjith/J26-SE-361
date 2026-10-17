
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DipRiskDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect() throws Exception {

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new DipRiskDetector().detect(parsed);
    }

    @Test
    void detectsConcreteFieldConstructionAcrossFiles()
            throws Exception {

        Files.writeString(
                root.resolve("SqlRepository.java"),
                """
                class SqlRepository {
                    void save() {}
                }
                """
        );

        Files.writeString(
                root.resolve("OrderService.java"),
                """
                class OrderService {
                    private final SqlRepository repository =
                            new SqlRepository();
                }
                """
        );

        var findings = detect();

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.DIP_RISK,
                findings.get(0).concern()
        );

        assertEquals(
                "SqlRepository",
                findings.get(0).evidence()
                        .get("declaredType")
        );
    }

    @Test
    void ignoresFieldTypedAsAbstraction()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                interface Storage {
                    void save();
                }

                class SqlStorage implements Storage {
                    public void save() {}
                }

                class OrderService {
                    private Storage storage = new SqlStorage();
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void ignoresLocalObjectConstruction()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                class Formatter {}

                class OrderService {
                    void run() {
                        Formatter formatter = new Formatter();
                    }
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void ignoresAbstractDependencyTypes()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                abstract class BaseStore {}

                class ConcreteStore extends BaseStore {}

                class OrderService {
                    private BaseStore store = new ConcreteStore();
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void producesDeterministicFindings()
            throws Exception {

        Files.writeString(
                root.resolve("Example.java"),
                """
                class ConcreteClient {}

                class AppService {
                    private ConcreteClient client =
                            new ConcreteClient();
                }
                """
        );

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new DipRiskDetector();

        assertEquals(
                detector.detect(parsed),
                detector.detect(parsed)
        );
    }
}
