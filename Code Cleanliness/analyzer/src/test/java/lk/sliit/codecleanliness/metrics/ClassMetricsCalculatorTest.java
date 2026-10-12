package lk.sliit.codecleanliness.metrics;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ClassMetricsCalculatorTest {

    private ClassMetrics measure(String source) {

        ClassOrInterfaceDeclaration declaration =
                StaticJavaParser.parse(source)
                        .findFirst(ClassOrInterfaceDeclaration.class)
                        .orElseThrow();

        return new ClassMetricsCalculator().calculate(declaration);
    }

    @Test
    void shouldMeasureSimpleClass() {

        ClassMetrics metrics = measure("""
                package example;

                public class Calculator {
                    private int value;
                    private String name;

                    public int add(int a, int b) {
                        return a + b;
                    }

                    public int getValue() {
                        if (value > 0) {
                            return value;
                        }
                        return 0;
                    }
                }
                """);

        assertEquals("example.Calculator",
                metrics.qualifiedClassName());

        assertEquals(2, metrics.methodCount());
        assertEquals(2, metrics.fieldCount());

        // add(): 1 statement
        // getValue(): if + 2 returns = 3 statements
        // fields: 2 variables
        assertEquals(6, metrics.classNcss());

        // add(): 1
        // getValue(): 2
        assertEquals(3, metrics.weightedMethodCount());
    }

    @Test
    void shouldCountMultipleVariablesInFieldDeclaration() {

        ClassMetrics metrics = measure("""
                package example;

                public class Inventory {
                    private int quantity, reserved, available;

                    public void reset() {
                        quantity = 0;
                    }
                }
                """);

        assertEquals(3, metrics.fieldCount());
        assertEquals(1, metrics.methodCount());
        assertEquals(4, metrics.classNcss());
        assertEquals(1, metrics.weightedMethodCount());
    }

    @Test
    void shouldHandleEmptyClass() {

        ClassMetrics metrics = measure("""
                package example;

                public class Empty {
                }
                """);

        assertEquals(0, metrics.methodCount());
        assertEquals(0, metrics.fieldCount());
        assertEquals(0, metrics.classNcss());
        assertEquals(0, metrics.weightedMethodCount());
    }
}