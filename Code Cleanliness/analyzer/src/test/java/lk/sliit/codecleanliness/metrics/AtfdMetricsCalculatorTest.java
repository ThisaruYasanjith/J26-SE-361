package lk.sliit.codecleanliness.metrics;

import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class AtfdMetricsCalculatorTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldCountDistinctForeignFieldsAcrossFiles()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(src.resolve("Customer.java"), """
                package example;
                public class Customer {
                    public int age;
                    public String name;
                }
                """);

        Files.writeString(src.resolve("CustomerService.java"), """
                package example;
                public class CustomerService {
                    private int localCount;

                    public void process(Customer customer) {
                        int a = customer.age;
                        int b = customer.age;
                        String n = customer.name;
                        localCount++;
                    }
                }
                """);

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        assertEquals(2, parsed.successfulFiles());

        var service = parsed.parsedFiles()
                .get(src.resolve("CustomerService.java"))
                .findFirst(ClassOrInterfaceDeclaration.class)
                .orElseThrow();

        AtfdMetrics metrics =
                new AtfdMetricsCalculator().calculate(service);

        assertEquals("example.Customer",
                "example.Customer");

        assertEquals(2, metrics.distinctForeignFields());
        assertTrue(metrics.foreignFieldReferences()
                .contains("example.Customer.age"));
        assertTrue(metrics.foreignFieldReferences()
                .contains("example.Customer.name"));
    }

    @Test
    void shouldIgnoreOwnFieldsAndLocalVariables()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(src.resolve("Counter.java"), """
                package example;
                public class Counter {
                    private int value;

                    public int calculate() {
                        int local = 5;
                        return value + local;
                    }
                }
                """);

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        var type = parsed.parsedFiles()
                .get(src.resolve("Counter.java"))
                .findFirst(ClassOrInterfaceDeclaration.class)
                .orElseThrow();

        AtfdMetrics metrics =
                new AtfdMetricsCalculator().calculate(type);

        assertEquals(0, metrics.distinctForeignFields());
    }
}