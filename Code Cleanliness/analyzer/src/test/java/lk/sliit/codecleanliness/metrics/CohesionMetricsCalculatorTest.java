package lk.sliit.codecleanliness.metrics;

import lk.sliit.codecleanliness.model.MethodUsageInfo;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CohesionMetricsCalculatorTest {

    private final CohesionMetricsCalculator calculator =
            new CohesionMetricsCalculator();

    private MethodUsageInfo usage(
            String method,
            List<String> fields,
            List<String> calls) {

        return new MethodUsageInfo(
                Path.of("Sample.java"),
                "example.Sample",
                method,
                1,
                fields,
                calls,
                List.of()
        );
    }

    @Test
    void shouldCalculateFullCohesion() {

        List<MethodUsageInfo> methods = List.of(
                usage("first()", List.of("value"), List.of()),
                usage("second()", List.of("value"), List.of()),
                usage("third()", List.of("value"), List.of())
        );

        CohesionMetrics result =
                calculator.calculate("example.Sample", methods);

        assertEquals(3, result.possibleMethodPairs());
        assertEquals(3, result.connectedMethodPairs());
        assertEquals(1.0, result.tcc(), 0.0001);
        assertEquals(1, result.lcom4());
    }

    @Test
    void shouldCalculateDisconnectedMethodGroups() {

        List<MethodUsageInfo> methods = List.of(
                usage("first()", List.of("value"), List.of()),
                usage("second()", List.of("value"), List.of()),
                usage("third()", List.of("other"), List.of())
        );

        CohesionMetrics result =
                calculator.calculate("example.Sample", methods);

        assertEquals(3, result.possibleMethodPairs());
        assertEquals(1, result.connectedMethodPairs());
        assertEquals(1.0 / 3.0, result.tcc(), 0.0001);
        assertEquals(2, result.lcom4());
    }

    @Test
    void shouldConnectMethodsThroughInternalCalls() {

        List<MethodUsageInfo> methods = List.of(
                usage(
                        "first()",
                        List.of("value"),
                        List.of("example.Sample.second()")
                ),
                usage("second()", List.of(), List.of()),
                usage("third()", List.of("other"), List.of())
        );

        CohesionMetrics result =
                calculator.calculate("example.Sample", methods);

        assertEquals(0.0, result.tcc(), 0.0001);
        assertEquals(2, result.lcom4());
    }

    @Test
    void shouldHandleClassWithoutMethods() {

        CohesionMetrics result =
                calculator.calculate("example.Empty", List.of());

        assertEquals(0, result.methodCount());
        assertEquals(0, result.lcom4());
        assertEquals(0.0, result.tcc(), 0.0001);
    }
}