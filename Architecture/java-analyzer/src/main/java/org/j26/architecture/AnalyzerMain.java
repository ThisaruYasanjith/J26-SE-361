package org.j26.architecture;

import java.io.IOException;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

public final class AnalyzerMain {
    private AnalyzerMain() {
    }

    public static void main(String[] args) {
        int exitCode = run(args, System.out, System.err);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    // Keeping the exit code separate lets tests check errors without stopping the JVM.
    static int run(String[] args, PrintStream output, PrintStream errors) {
        if (args.length == 0 || args[0].isBlank()) {
            errors.println("Error: supply the Spring Boot project directory.");
            errors.println("Usage: java -jar java-analyzer.jar \"<project-path>\"");
            return 2;
        }

        try {
            Path projectRoot = Path.of(args[0]).toAbsolutePath().normalize();
            if (!Files.exists(projectRoot)) {
                errors.println("Error: project path does not exist: " + projectRoot);
                return 2;
            }
            if (!Files.isDirectory(projectRoot)) {
                errors.println("Error: project path is not a directory: " + projectRoot);
                return 2;
            }

            JavaProjectScanner.ScanResult result = new JavaProjectScanner().scan(projectRoot);
            for (JavaProjectScanner.ParseFailure failure : result.parseFailures()) {
                errors.println("Failed to parse " + failure.filePath() + ": " + failure.message());
            }

            String projectName = projectRoot.getFileName() == null
                    ? projectRoot.toString() : projectRoot.getFileName().toString();
            output.println("Project: " + projectName);
            output.println("Java files found: " + result.javaFiles().size());
            output.println("Successfully parsed: " + result.successfullyParsed());
            output.println("Parse failures: " + result.parseFailures().size());

            // A partial scan still prints its summary, but scripts can detect the failures.
            return result.parseFailures().isEmpty() ? 0 : 1;
        } catch (InvalidPathException exception) {
            errors.println("Error: invalid project path: " + exception.getMessage());
            return 2;
        } catch (IOException | SecurityException exception) {
            errors.println("Error: unable to scan the project: " + exception.getMessage());
            return 1;
        }
    }
}
