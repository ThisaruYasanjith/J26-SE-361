package org.j26.architecture;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JavaProjectScannerTest {
    @TempDir
    Path project;

    private final JavaProjectScanner scanner = new JavaProjectScanner();

    @Test
    void prefersMainSourcesOverTestsAndOtherJavaFiles() throws IOException {
        Path controller = write("src/main/java/demo/PaymentController.java", "class PaymentController {}");
        write("src/test/java/demo/PaymentTest.java", "class PaymentTest {}");
        write("Other.java", "class Other {}");

        assertEquals(List.of(controller), scanner.discoverJavaFiles(project));
    }

    @Test
    void fallsBackToTheSuppliedDirectoryAndSortsPaths() throws IOException {
        Path last = write("nested/Zebra.java", "class Zebra {}");
        Path first = write("nested/Alpha.java", "class Alpha {}");
        write("nested/notes.txt", "not Java");

        assertEquals(List.of(first, last), scanner.discoverJavaFiles(project));
        assertEquals(List.of(first, last), scanner.discoverJavaFiles(project));
    }

    @Test
    void skipsIgnoredDirectoriesAtAnyDepth() throws IOException {
        Path source = write("Source.java", "class Source {}");
        for (String directory : List.of("target", "build", "out", ".git", "node_modules", "dist")) {
            write(directory + "/Generated.java", "class Generated {}");
            write("nested/" + directory + "/Generated.java", "class Generated {}");
        }

        assertEquals(List.of(source), scanner.discoverJavaFiles(project));
    }

    @Test
    void skipsIgnoredDirectoriesInsideMainSources() throws IOException {
        Path source = write("src/main/java/demo/Source.java", "class Source {}");
        write("src/main/java/demo/target/Generated.java", "class Generated {}");

        assertEquals(List.of(source), scanner.discoverJavaFiles(project));
    }

    @Test
    void doesNotFallBackWhenMainSourcesExistButAreEmpty() throws IOException {
        Files.createDirectories(project.resolve("src/main/java"));
        write("Other.java", "class Other {}");

        assertTrue(scanner.discoverJavaFiles(project).isEmpty());
    }

    @Test
    void parsesSpringStyleSourcesAndJava17SyntaxWithoutResolvingImports() throws IOException {
        // Syntax parsing should work even when the sample project's dependencies are not installed.
        write("src/main/java/demo/PaymentController.java", """
                package demo;
                import org.springframework.web.bind.annotation.RestController;
                @RestController
                class PaymentController {}
                """);
        write("src/main/java/demo/Payment.java", "package demo; record Payment(String reference) {}");

        JavaProjectScanner.ScanResult result = scanner.scan(project);

        assertEquals(2, result.javaFiles().size());
        assertEquals(2, result.successfullyParsed());
        assertTrue(result.parseFailures().isEmpty());
    }

    @Test
    void continuesAfterAnInvalidFileAndKeepsItsError() throws IOException {
        Path broken = write("ABroken.java", "class ABroken { void broken( }");
        write("ZValid.java", "class ZValid {}");

        JavaProjectScanner.ScanResult result = scanner.scan(project);

        assertEquals(2, result.javaFiles().size());
        assertEquals(1, result.successfullyParsed());
        assertEquals(1, result.parseFailures().size());
        assertEquals(broken, result.parseFailures().get(0).filePath());
        assertFalse(result.parseFailures().get(0).message().isBlank());
    }

    @Test
    void handlesAnEmptyProject() throws IOException {
        JavaProjectScanner.ScanResult result = scanner.scan(project);

        assertTrue(result.javaFiles().isEmpty());
        assertEquals(0, result.successfullyParsed());
        assertTrue(result.parseFailures().isEmpty());
    }

    @Test
    void rejectsInvalidScannerRoots() throws IOException {
        Path file = write("Source.java", "class Source {}");

        assertThrows(IOException.class, () -> scanner.discoverJavaFiles(project.resolve("missing")));
        assertThrows(IOException.class, () -> scanner.discoverJavaFiles(file));
    }

    @Test
    void cliExplainsMissingInvalidAndNonDirectoryPaths() throws IOException {
        ByteArrayOutputStream messages = new ByteArrayOutputStream();
        try (PrintStream output = new PrintStream(messages, true, StandardCharsets.UTF_8)) {
            assertEquals(2, AnalyzerMain.run(new String[0], output, output));
            assertEquals(2, AnalyzerMain.run(new String[]{" "}, output, output));
            assertEquals(2, AnalyzerMain.run(new String[]{"\u0000"}, output, output));
            assertEquals(2, AnalyzerMain.run(new String[]{project.resolve("missing").toString()}, output, output));
            Path file = write("Source.java", "class Source {}");
            assertEquals(2, AnalyzerMain.run(new String[]{file.toString()}, output, output));
        }

        String text = messages.toString(StandardCharsets.UTF_8);
        assertTrue(text.contains("Usage:"));
        assertTrue(text.contains("invalid project path"));
        assertTrue(text.contains("does not exist"));
        assertTrue(text.contains("not a directory"));
    }

    @Test
    void cliPrintsSummaryAndFailureDetails() throws IOException {
        Path broken = write("ABroken.java", "class ABroken { void broken( }");
        write("ZValid.java", "class ZValid {}");
        ByteArrayOutputStream summary = new ByteArrayOutputStream();
        ByteArrayOutputStream errors = new ByteArrayOutputStream();

        try (PrintStream output = new PrintStream(summary, true, StandardCharsets.UTF_8);
             PrintStream errorOutput = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
            assertEquals(1, AnalyzerMain.run(new String[]{project.toString()}, output, errorOutput));
        }

        String text = summary.toString(StandardCharsets.UTF_8);
        assertTrue(text.contains("Java files found: 2"));
        assertTrue(text.contains("Successfully parsed: 1"));
        assertTrue(text.contains("Parse failures: 1"));
        assertTrue(errors.toString(StandardCharsets.UTF_8).contains(broken.toString()));
        assertFalse(Files.exists(project.resolve("project_context.json")));
    }

    @Test
    void cliReturnsSuccessForAValidProject() throws IOException {
        write("Source.java", "class Source {}");
        ByteArrayOutputStream messages = new ByteArrayOutputStream();
        try (PrintStream output = new PrintStream(messages, true, StandardCharsets.UTF_8)) {
            assertEquals(0, AnalyzerMain.run(new String[]{project.toString()}, output, output));
        }

        assertTrue(messages.toString(StandardCharsets.UTF_8).contains("Parse failures: 0"));
    }

    private Path write(String relativePath, String content) throws IOException {
        Path file = project.resolve(relativePath);
        Files.createDirectories(file.getParent());
        return Files.writeString(file, content, StandardCharsets.UTF_8);
    }
}
