
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.triage.RepositoryTriageService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class SolidRiskIntegrationTest {

    @TempDir
    Path root;

    private RepositoryDetectionConfig config(
            boolean enableSolid) {

        return new RepositoryDetectionConfig(
                new MethodDetectionThresholds(1000, 1000),
                new ClassDetectionThresholds(1000, 1000, 1000),
                new CohesionDetectionThresholds(0.0, 1000),
                new GodClassDetectionThresholds(1000, 1000, 0.0),
                null,
                null,
                enableSolid
        );
    }

    private void createRepository() throws Exception {

        Files.writeString(
                root.resolve("SolidExamples.java"),
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

                class ParentTask {
                    void execute() {}
                }

                class ChildTask extends ParentTask {
                    @Override
                    void execute() {
                        throw new UnsupportedOperationException();
                    }
                }

                class ConcreteRepository {
                    void save() {}
                }

                class OrderService {
                    private final ConcreteRepository repository =
                            new ConcreteRepository();
                }

                class CardPayment {}
                class CashPayment {}
                class BankPayment {}

                class PaymentProcessor {
                    void process(Object payment) {
                        if (payment instanceof CardPayment) {}
                        if (payment instanceof CashPayment) {}
                        if (payment instanceof BankPayment) {}
                    }
                }

                class CombinedManager {
                    private int customerCount;
                    private int invoiceCount;

                    void addCustomer() {
                        customerCount++;
                    }

                    void removeCustomer() {
                        customerCount--;
                    }

                    void addInvoice() {
                        invoiceCount++;
                    }

                    void removeInvoice() {
                        invoiceCount--;
                    }
                }
                """
        );
    }

    @Test
    void integratesAllFiveSolidRiskConcerns()
            throws Exception {

        createRepository();

        var result = new RepositoryTriageService()
                .analyze(root, config(true));

        Set<MaintainabilityConcern> concerns =
                result.analysis()
                        .findings()
                        .stream()
                        .map(finding -> finding.concern())
                        .collect(Collectors.toSet());

        assertTrue(concerns.contains(
                MaintainabilityConcern.SRP_RISK));

        assertTrue(concerns.contains(
                MaintainabilityConcern.OCP_RISK));

        assertTrue(concerns.contains(
                MaintainabilityConcern.LSP_RISK));

        assertTrue(concerns.contains(
                MaintainabilityConcern.ISP_RISK));

        assertTrue(concerns.contains(
                MaintainabilityConcern.DIP_RISK));
    }

    @Test
    void disablesSolidRisksWhenNotConfigured()
            throws Exception {

        createRepository();

        var result = new RepositoryTriageService()
                .analyze(root, config(false));

        assertTrue(
                result.analysis().findings().stream()
                        .noneMatch(finding ->
                                isSolidConcern(finding.concern()))
        );
    }

    @Test
    void producesDeterministicRepositoryTriage()
            throws Exception {

        createRepository();

        var service = new RepositoryTriageService();

        var first = service.analyze(root, config(true));
        var second = service.analyze(root, config(true));

        assertEquals(
                first.analysis().findings(),
                second.analysis().findings()
        );

        assertEquals(
                first.rankedGroups().size(),
                second.rankedGroups().size()
        );
    }

    private boolean isSolidConcern(
            MaintainabilityConcern concern) {

        return concern == MaintainabilityConcern.SRP_RISK
                || concern == MaintainabilityConcern.OCP_RISK
                || concern == MaintainabilityConcern.LSP_RISK
                || concern == MaintainabilityConcern.ISP_RISK
                || concern == MaintainabilityConcern.DIP_RISK;
    }
}
