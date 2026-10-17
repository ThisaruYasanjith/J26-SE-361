
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class OcpRiskDetectorTest {

    @TempDir
    Path root;

    private java.util.List<
            lk.sliit.codecleanliness.model.MaintainabilityFinding
            > detect() throws Exception {

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        return new OcpRiskDetector().detect(repository);
    }

    private void writePaymentTypes() throws Exception {

        Files.writeString(root.resolve("CardPayment.java"),
                "class CardPayment {}");

        Files.writeString(root.resolve("CashPayment.java"),
                "class CashPayment {}");

        Files.writeString(root.resolve("BankPayment.java"),
                "class BankPayment {}");
    }

    @Test
    void detectsRepeatedTypeChecksAcrossFiles()
            throws Exception {

        writePaymentTypes();

        Files.writeString(
                root.resolve("PaymentProcessor.java"),
                """
                class PaymentProcessor {
                    void process(Object payment) {
                        if (payment instanceof CardPayment) {
                            System.out.println("card");
                        } else if (payment instanceof CashPayment) {
                            System.out.println("cash");
                        } else if (payment instanceof BankPayment) {
                            System.out.println("bank");
                        }
                    }
                }
                """
        );

        var findings = detect();

        assertEquals(1, findings.size());

        assertEquals(
                MaintainabilityConcern.OCP_RISK,
                findings.get(0).concern()
        );

        assertEquals(
                "3",
                findings.get(0).evidence()
                        .get("distinctTypeCount")
        );
    }

    @Test
    void ignoresSingleTypeCheck() throws Exception {

        writePaymentTypes();

        Files.writeString(
                root.resolve("PaymentProcessor.java"),
                """
                class PaymentProcessor {
                    boolean accepts(Object payment) {
                        return payment instanceof CardPayment;
                    }
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void ignoresChecksOnDifferentExpressions()
            throws Exception {

        writePaymentTypes();

        Files.writeString(
                root.resolve("PaymentProcessor.java"),
                """
                class PaymentProcessor {
                    void process(Object first,
                                 Object second,
                                 Object third) {

                        boolean a =
                                first instanceof CardPayment;

                        boolean b =
                                second instanceof CashPayment;

                        boolean c =
                                third instanceof BankPayment;
                    }
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void ignoresUnknownConcreteTypes()
            throws Exception {

        Files.writeString(
                root.resolve("PaymentProcessor.java"),
                """
                class PaymentProcessor {
                    void process(Object payment) {
                        if (payment instanceof UnknownCard) {}
                        if (payment instanceof UnknownCash) {}
                        if (payment instanceof UnknownBank) {}
                    }
                }
                """
        );

        assertTrue(detect().isEmpty());
    }

    @Test
    void resultsAreDeterministic() throws Exception {

        writePaymentTypes();

        Files.writeString(
                root.resolve("PaymentProcessor.java"),
                """
                class PaymentProcessor {
                    void process(Object payment) {
                        if (payment instanceof CardPayment) {}
                        if (payment instanceof CashPayment) {}
                        if (payment instanceof BankPayment) {}
                    }
                }
                """
        );

        var repository = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(root);

        var detector = new OcpRiskDetector();

        assertEquals(
                detector.detect(repository),
                detector.detect(repository)
        );
    }
}
