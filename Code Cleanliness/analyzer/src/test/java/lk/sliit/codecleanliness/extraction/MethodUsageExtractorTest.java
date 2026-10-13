package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.model.MethodUsageInfo;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MethodUsageExtractorTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldExtractFieldUsageAndInternalMethodCalls()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Account.java"),
                """
                package example;

                public class Account {
                    private int balance;
                    private String owner;

                    public void deposit(int amount) {
                        balance += amount;
                        audit();
                    }

                    public int getBalance() {
                        return this.balance;
                    }

                    private void audit() {
                        System.out.println(owner);
                    }
                }
                """
        );

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        assertEquals(1, parsed.successfulFiles());

        List<MethodUsageInfo> usages =
                new MethodUsageExtractor().extract(parsed);

        assertEquals(3, usages.size());

        MethodUsageInfo deposit = usages.stream()
                .filter(m -> m.methodSignature()
                        .equals("deposit(int)"))
                .findFirst()
                .orElseThrow();

        assertTrue(deposit.accessedFields()
                .contains("balance"));

        assertTrue(deposit.calledMethods().stream()
                .anyMatch(call -> call.contains(
                        "example.Account.audit()"
                )));

        MethodUsageInfo getBalance = usages.stream()
                .filter(m -> m.methodSignature()
                        .equals("getBalance()"))
                .findFirst()
                .orElseThrow();

        assertTrue(getBalance.accessedFields()
                .contains("balance"));

        MethodUsageInfo audit = usages.stream()
                .filter(m -> m.methodSignature()
                        .equals("audit()"))
                .findFirst()
                .orElseThrow();

        assertTrue(audit.accessedFields()
                .contains("owner"));
    }

    @Test
    void shouldNotConfuseLocalVariableWithClassField()
            throws IOException {

        Path src = Files.createDirectories(
                tempDir.resolve("src/main/java/example")
        );

        Files.writeString(
                src.resolve("Counter.java"),
                """
                package example;

                public class Counter {
                    private int count;

                    public int calculate() {
                        int count = 10;
                        return count;
                    }
                }
                """
        );

        var parsed = new JavaRepositoryParser()
                .parseRepositoryWithSymbols(tempDir);

        List<MethodUsageInfo> usages =
                new MethodUsageExtractor().extract(parsed);

        assertEquals(1, usages.size());

        assertFalse(usages.get(0)
                .accessedFields().contains("count"));
    }
}