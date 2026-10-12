package lk.sliit.codecleanliness.metrics;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.body.MethodDeclaration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MethodMetricsCalculatorTest {

    private MethodMetrics measure(String methodSource) {

        MethodDeclaration method =
                StaticJavaParser.parseBodyDeclaration(methodSource)
                        .asMethodDeclaration();

        return new MethodMetricsCalculator().calculate(method);
    }

    @Test
    void shouldMeasureSimpleMethod() {

        MethodMetrics metrics = measure("""
                public int sum(int a, int b) {
                    int result = a + b;
                    return result;
                }
                """);

        assertEquals(2, metrics.ncss());
        assertEquals(1, metrics.cyclomaticComplexity());
    }

    @Test
    void shouldMeasureIfElseComplexity() {

        MethodMetrics metrics = measure("""
                public int classify(int number) {
                    if (number > 0) {
                        return 1;
                    } else {
                        return -1;
                    }
                }
                """);

        assertEquals(3, metrics.ncss());
        assertEquals(2, metrics.cyclomaticComplexity());
    }

    @Test
    void shouldMeasureLoopAndLogicalOperators() {

        MethodMetrics metrics = measure("""
                public void process(int[] values) {
                    for (int value : values) {
                        if (value > 0 && value < 100) {
                            System.out.println(value);
                        }
                    }
                }
                """);

        assertEquals(3, metrics.ncss());
        assertEquals(4, metrics.cyclomaticComplexity());
    }

    @Test
    void shouldHandleAbstractMethod() {

        MethodMetrics metrics = measure("""
                public abstract void execute();
                """);

        assertEquals(0, metrics.ncss());
        assertEquals(0, metrics.cyclomaticComplexity());
    }
}
